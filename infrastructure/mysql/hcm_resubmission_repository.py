"""MySQL adapter for canonical HCM review resubmission."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from domains.case_import.hcm_resubmission import HcmResubmissionFacts, hcm_field_targets
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.case_import.hcm_resubmission_workflow import HcmResubmissionReceipt


class MySqlHcmResubmissionRepository:
    def __init__(self, connection, client_port=None, orders_port=None) -> None:
        self._connection = connection
        self._client_port = client_port
        self._orders_port = orders_port

    def load_facts(self, review_identity: str, *, for_update: bool) -> HcmResubmissionFacts:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_FACTS_SQL + suffix, (review_identity,))
            row = cursor.fetchone()
        if row is None:
            raise ValueError("hcm_resubmission_not_available")
        logical_code, field_path = _single_owned_field(row["issue_codes"])
        targets = hcm_field_targets(field_path)
        values = {target: row[_column_alias(target)] for target in targets}
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(resulting_review_version),0) AS review_version "
                "FROM case_import_hcm_correction_events WHERE canonical_review_identity=%s",
                (review_identity,),
            )
            version_row = cursor.fetchone() or {}
        review_version = int(version_row.get("review_version") or 0)
        client_version = int(row.get("client_hcm_correction_version") or 0)
        order_version = int(row.get("order_version") or 0)
        root_fingerprint = fingerprint_payload({
            "target_values": values, "client_version": client_version,
            "order_version": order_version, "review_identity": str(row["review_identity"]),
            "review_version": review_version,
        }).value
        return HcmResubmissionFacts(
            review_identity=str(row["review_identity"]), logical_code=logical_code,
            field_path=field_path, case_no=str(row["case_no"]), client_id=int(row["client_id"]),
            review_binding_id=int(row["binding_id"]),
            prior_source_event_identity=str(row["prior_source_event_identity"]),
            review_version=review_version, root_fingerprint=root_fingerprint,
            client_version=client_version, order_version=order_version,
        )

    def load_holiday_dates(self) -> set[date]:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT holiday_date FROM holidays")
            rows = cursor.fetchall()
        return {value for row in rows if isinstance((value := row["holiday_date"]), date)}

    def readback(self, case_no: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS client_id,c.case_no,c.client_hcm_correction_version,"
                "o.lifecycle_version AS order_version,o.end_date,o.actual_end_date "
                "FROM clients c JOIN orders o ON o.case_no=c.case_no WHERE c.case_no=%s", (case_no,))
            row = cursor.fetchone()
        if row is None:
            raise ValueError("hcm_resubmission_readback_missing")
        return dict(row)

    def find_receipt(self, idempotency_key: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM case_import_hcm_correction_receipts WHERE idempotency_key=%s",
                (idempotency_key,))
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _json_object(row["result_snapshot"])
        return str(row["command_fingerprint"]), HcmResubmissionReceipt(
            str(payload["event_identity"]), str(payload["review_identity"]), str(payload["case_no"]),
            tuple(str(item) for item in payload["target_fields"]), int(payload["resulting_review_version"]), False)

    def apply_field_correction(self, candidate, source, *, actor: str, reason: str,
                               correlation_id: str, client_command=None) -> str:
        facts = self.load_facts(candidate.review_identity, for_update=True)
        if facts.case_no != candidate.case_no:
            raise ValueError("hcm_resubmission_binding_integrity_failed")
        if client_command is not None:
            if self._client_port is None:
                raise ValueError("client_hcm_correction_owner_unavailable")
            self._client_port.apply_in_current_uow(client_command)
        order_values = {key: value for key, value in candidate.target_values.items() if key.startswith("orders.")}
        if order_values:
            if self._orders_port is None:
                raise ValueError("orders_hcm_correction_owner_unavailable")
            self._orders_port.apply_in_current_uow(
                candidate.case_no, order_values, source_event_identity=source.source_event_identity,
                actor=actor, reason=reason, correlation_id=correlation_id,
                idempotency_key=source.source_event_identity)
        after = self.load_facts(candidate.review_identity, for_update=True)
        resulting_review_version = facts.review_version + 1
        event_identity = _identity(
            "hcm-correction-event",
            f"{candidate.review_identity}:{source.source_event_identity}:{source.source_fingerprint}")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO case_import_hcm_correction_events "
                "(event_identity,case_no,client_id,review_binding_id,canonical_review_identity,"
                "expected_review_version,resulting_review_version,prior_occurrence_id,source_event_identity,"
                "source_fingerprint,candidate_fingerprint,adopted_field_paths,root_before_fingerprint,"
                "root_after_fingerprint,actor,reason,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (event_identity, facts.case_no, facts.client_id, facts.review_binding_id,
                 facts.review_identity, facts.review_version, resulting_review_version,
                 None, source.source_event_identity, source.source_fingerprint,
                 fingerprint_payload(candidate.target_values).value, _json([candidate.source_field]),
                 facts.root_fingerprint, after.root_fingerprint, actor, reason, correlation_id))
        return event_identity

    def save_receipt(self, idempotency_key: str, command_fingerprint: str,
                     preview_fingerprint: str, receipt: HcmResubmissionReceipt) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM case_import_hcm_correction_events WHERE event_identity=%s", (receipt.event_identity,))
            event = cursor.fetchone()
            if event is None:
                raise RuntimeError("hcm_resubmission_event_missing")
            cursor.execute(
                "INSERT INTO case_import_hcm_correction_receipts "
                "(idempotency_key,command_fingerprint,preview_fingerprint,correction_event_id,result_snapshot) VALUES (%s,%s,%s,%s,%s)",
                (idempotency_key, command_fingerprint, preview_fingerprint, int(event["id"]), _json({
                    "event_identity": receipt.event_identity, "review_identity": receipt.review_identity,
                    "case_no": receipt.case_no, "target_fields": receipt.target_fields,
                    "resulting_review_version": receipt.resulting_review_version})))

    def append_outbox(self, event_identity: str, review_identity: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM case_import_hcm_correction_events WHERE event_identity=%s", (event_identity,))
            event = cursor.fetchone()
            if event is None:
                raise RuntimeError("hcm_resubmission_event_missing")
            cursor.execute(
                "INSERT INTO case_import_hcm_correction_outbox (correction_event_id,intent_key,bounded_snapshot) VALUES (%s,%s,%s)",
                (int(event["id"]), _identity("hcm-correction-outbox", event_identity), _json({
                    "event_identity": event_identity, "review_identity": review_identity})))


def _column_alias(target: str) -> str:
    return target.replace(".", "_")


def _table_alias(target: str) -> str:
    return {"clients": "c", "orders": "ord"}[target.split(".", 1)[0]]


def _identity(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def _json_object(value: object) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("hcm_resubmission_receipt_invalid")
    return parsed


def _single_owned_field(value: object) -> tuple[str, str]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("hcm_resubmission_review_issue_codes_invalid")
    field_codes = [str(item) for item in parsed if isinstance(item, str) and (
        item.startswith("hcm_field_missing:") or item.startswith("hcm_field_invalid:"))]
    field_paths = {item.split(":", 1)[1].strip() for item in field_codes if ":" in item and item.split(":", 1)[1].strip()}
    if len(field_paths) != 1:
        raise ValueError("hcm_resubmission_review_scope_ambiguous")
    field_path = next(iter(field_paths))
    logical_codes = {"HCM-FIELD-001" if item.startswith("hcm_field_missing:") else "HCM-FIELD-002"
                     for item in field_codes if item.endswith(":" + field_path)}
    if len(logical_codes) != 1:
        raise ValueError("hcm_resubmission_review_scope_ambiguous")
    hcm_field_targets(field_path)
    return next(iter(logical_codes)), field_path


_TARGET_SELECTS = ",".join(
    f"{_table_alias(target)}.{target.split('.', 1)[1]} AS {_column_alias(target)}"
    for target in sorted({target for fields in (
        hcm_field_targets("報名時間(建檔)"), hcm_field_targets("IP位址"), hcm_field_targets("姓名"),
        hcm_field_targets("性別"), hcm_field_targets("行動電話"), hcm_field_targets("縣市"),
        hcm_field_targets("預產期/預計服務開始月份"), hcm_field_targets("居住型態"),
        hcm_field_targets("生產方式"), hcm_field_targets("寶寶資訊"), hcm_field_targets("服務時間"),
        hcm_field_targets("預計服務日期"), hcm_field_targets("希望服務天數"), hcm_field_targets("服務方式"),
    ) for target in fields})
)
_FACTS_SQL = (
    "SELECT b.id AS binding_id,b.case_no,e.client_id,r.review_identity,r.issue_codes,"
    "r.source_event_identity AS prior_source_event_identity,c.client_hcm_correction_version,"
    "ord.lifecycle_version AS order_version," + _TARGET_SELECTS + " FROM case_import_hcm_review_rows r "
    "JOIN case_import_hcm_review_case_bindings b ON b.review_row_id=r.id "
    "JOIN case_import_events e ON e.id=b.root_import_event_id AND e.case_no=b.case_no "
    "JOIN clients c ON c.id=e.client_id AND c.case_no=b.case_no "
    "JOIN orders ord ON ord.case_no=b.case_no WHERE r.review_identity=%s"
)

__all__ = ["MySqlHcmResubmissionRepository"]

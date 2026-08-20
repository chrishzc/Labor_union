"""
File: hcm_resubmission_repository.py
Description: 以 warning→review→binding 鎖定 HCM 單欄修正與 immutable owner evidence。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

from domains.case_import.hcm_resubmission import HcmResubmissionFacts, hcm_field_targets
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.case_import.hcm_resubmission_workflow import HcmResubmissionReceipt


class MySqlHcmResubmissionRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load_facts(self, occurrence_identity: str, *, for_update: bool) -> HcmResubmissionFacts:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_FACTS_SQL + suffix, (occurrence_identity,))
            row = cursor.fetchone()
        if row is None:
            raise ValueError("hcm_resubmission_not_available")
        targets = hcm_field_targets(str(row["field_path"]))
        values = {target: row[_column_alias(target)] for target in targets}
        return HcmResubmissionFacts(
            occurrence_identity=str(row["occurrence_identity"]),
            occurrence_id=int(row["occurrence_id"]),
            logical_code=str(row["logical_code"]),
            field_path=str(row["field_path"]),
            case_no=str(row["case_no"]),
            client_id=int(row["client_id"]),
            review_binding_id=int(row["binding_id"]),
            prior_source_event_identity=str(row["prior_source_event_identity"]),
            occurrence_version=int(row["tracking_version"]),
            root_fingerprint=fingerprint_payload(values).value,
        )

    def load_holiday_dates(self) -> set[date]:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT holiday_date FROM holidays")
            rows = cursor.fetchall()
        return {
            value
            for row in rows
            if isinstance((value := row["holiday_date"]), date)
        }

    def find_receipt(self, idempotency_key: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM case_import_hcm_correction_receipts "
                "WHERE idempotency_key=%s",
                (idempotency_key,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _json_object(row["result_snapshot"])
        return str(row["command_fingerprint"]), HcmResubmissionReceipt(
            str(payload["event_identity"]),
            str(payload["occurrence_identity"]),
            str(payload["case_no"]),
            tuple(str(item) for item in payload["target_fields"]),
            False,
        )

    def apply_field_correction(self, candidate, source, *, actor: str, reason: str, correlation_id: str) -> str:
        facts = self.load_facts(candidate.occurrence_identity, for_update=True)
        if facts.case_no != candidate.case_no:
            raise ValueError("hcm_resubmission_binding_integrity_failed")
        _apply_targets(self._connection, facts, candidate.target_values)
        after = self.load_facts(candidate.occurrence_identity, for_update=True)
        event_identity = _identity(
            "hcm-correction-event",
            f"{candidate.occurrence_identity}:{source.source_event_identity}:{source.source_fingerprint}",
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO case_import_hcm_correction_events "
                "(event_identity,case_no,client_id,review_binding_id,prior_occurrence_id,source_event_identity,"
                "source_fingerprint,candidate_fingerprint,adopted_field_paths,root_before_fingerprint,"
                "root_after_fingerprint,actor,reason,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (event_identity, facts.case_no, facts.client_id, facts.review_binding_id, facts.occurrence_id,
                 source.source_event_identity, source.source_fingerprint,
                 fingerprint_payload(candidate.target_values).value, _json([candidate.source_field]),
                 facts.root_fingerprint, after.root_fingerprint,
                 actor, reason, correlation_id),
            )
            cursor.execute(
                "INSERT INTO import_warning_resubmission_associations "
                "(association_identity,prior_occurrence_id,owning_lane,prior_source_event_identity,"
                "new_source_event_identity,new_receipt_identity,import_outcome) "
                "VALUES (%s,%s,'hcm',%s,%s,%s,'succeeded')",
                (
                    _identity("hcm-resubmission-association", f"{candidate.occurrence_identity}:{source.source_event_identity}"),
                    facts.occurrence_id, facts.prior_source_event_identity, source.source_event_identity, event_identity,
                ),
            )
        return event_identity

    def save_receipt(
        self,
        idempotency_key: str,
        command_fingerprint: str,
        preview_fingerprint: str,
        receipt: HcmResubmissionReceipt,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM case_import_hcm_correction_events WHERE event_identity=%s", (receipt.event_identity,))
            event = cursor.fetchone()
            if event is None:
                raise RuntimeError("hcm_resubmission_event_missing")
            cursor.execute(
                "INSERT INTO case_import_hcm_correction_receipts "
                "(idempotency_key,command_fingerprint,preview_fingerprint,correction_event_id,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s)",
                (idempotency_key, command_fingerprint, preview_fingerprint, int(event["id"]), _json({
                    "event_identity": receipt.event_identity, "occurrence_identity": receipt.occurrence_identity,
                    "case_no": receipt.case_no, "target_fields": receipt.target_fields,
                })),
            )

    def append_outbox(self, event_identity: str, occurrence_identity: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM case_import_hcm_correction_events WHERE event_identity=%s", (event_identity,))
            event = cursor.fetchone()
            if event is None:
                raise RuntimeError("hcm_resubmission_event_missing")
            cursor.execute(
                "INSERT INTO case_import_hcm_correction_outbox (correction_event_id,intent_key,bounded_snapshot) "
                "VALUES (%s,%s,%s)",
                (int(event["id"]), _identity("hcm-correction-outbox", event_identity), _json({
                    "event_identity": event_identity, "occurrence_identity": occurrence_identity,
                })),
            )


def _apply_targets(connection, facts: HcmResubmissionFacts, target_values) -> None:
    grouped = {"clients": {}, "orders": {}}
    for target, value in target_values.items():
        table, column = str(target).split(".", 1)
        if table not in grouped or target not in hcm_field_targets(facts.field_path):
            raise ValueError("hcm_resubmission_target_values_invalid")
        grouped[table][column] = value
    with connection.cursor() as cursor:
        for table, values in grouped.items():
            if not values:
                continue
            assignments = ",".join(f"`{column}`=%s" for column in sorted(values))
            predicate = "id=%s" if table == "clients" else "case_no=%s"
            identifier = facts.client_id if table == "clients" else facts.case_no
            cursor.execute(f"UPDATE {table} SET {assignments} WHERE {predicate}", (*[values[column] for column in sorted(values)], identifier))
            if int(cursor.rowcount) > 1:
                raise ValueError("hcm_resubmission_root_write_conflict")


def _column_alias(target: str) -> str:
    return target.replace(".", "_")


def _table_alias(target: str) -> str:
    return {"clients": "c", "orders": "ord"}[target.split(".", 1)[0]]


def _identity(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_object(value: object) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("hcm_resubmission_receipt_invalid")
    return parsed


_TARGET_SELECTS = ",".join(
    f"{_table_alias(target)}.{target.split('.', 1)[1]} AS {_column_alias(target)}"
    for target in sorted({target for fields in (
        hcm_field_targets("報名時間(建檔)"), hcm_field_targets("IP位址"), hcm_field_targets("姓名"),
        hcm_field_targets("性別"), hcm_field_targets("行動電話"), hcm_field_targets("縣市"),
        hcm_field_targets("身分資格"), hcm_field_targets("預產期/預計服務開始月份"),
        hcm_field_targets("居住型態"), hcm_field_targets("生產方式"), hcm_field_targets("寶寶資訊"),
        hcm_field_targets("服務時間"), hcm_field_targets("預計服務日期"), hcm_field_targets("希望服務天數"),
        hcm_field_targets("服務方式"),
    ) for target in fields})
)
_FACTS_SQL = (
    "SELECT o.id AS occurrence_id,o.occurrence_identity,o.logical_code,o.field_path,t.tracking_version,"
    "b.id AS binding_id,b.case_no,e.client_id,r.source_event_identity AS prior_source_event_identity,"
    + _TARGET_SELECTS + " FROM import_warning_current_tasks t "
    "JOIN import_warning_occurrences o ON o.id=t.occurrence_id "
    "JOIN case_import_hcm_review_rows r ON r.review_identity=o.source_receipt_identity "
    "AND r.source_event_identity=o.source_event_identity "
    "JOIN case_import_hcm_review_case_bindings b ON b.review_row_id=r.id "
    "JOIN case_import_events e ON e.id=b.root_import_event_id AND e.case_no=b.case_no "
    "JOIN clients c ON c.id=e.client_id AND c.case_no=b.case_no "
    "JOIN orders ord ON ord.case_no=b.case_no "
    "WHERE o.occurrence_identity=%s AND o.owning_lane='hcm' "
    "AND t.tracking_status NOT IN ('closed','auto_resolved')"
)


__all__ = ["MySqlHcmResubmissionRepository"]

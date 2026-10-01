"""MySQL adapter for canonical HCM review resubmission."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from domains.case_import.hcm_resubmission import HcmResubmissionFacts, hcm_field_targets
from domains.case_import.hcm_import_review import (
    HCM_SKIP_REJECT_REASON_PATH, HCM_SKIP_FIELD_PREFIX, hcm_field_skip_path, unresolved_hcm_review_fields,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.case_import.hcm_resubmission_workflow import HcmResubmissionReceipt, HcmReviewSkipFacts


class MySqlHcmResubmissionRepository:
    def __init__(self, connection, client_port=None, orders_port=None) -> None:
        self._connection = connection
        self._client_port = client_port
        self._orders_port = orders_port

    def _load_review_row(self, review_identity: str, *, for_update: bool = False):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_FACTS_SQL + suffix, (review_identity,))
            row = cursor.fetchone()
        if row is None:
            raise ValueError("hcm_resubmission_not_available")
        return row

    def load_facts(self, review_identity: str, *, for_update: bool, resulting_review_version: int | None = None) -> HcmResubmissionFacts:
        row = self._load_review_row(review_identity, for_update=for_update)
        return self._facts_from_row(row, resulting_review_version=resulting_review_version)

    def _facts_from_row(self, row, *, resulting_review_version: int | None = None) -> HcmResubmissionFacts:
        logical_code, field_path = _single_owned_field(row["issue_codes"])
        targets = hcm_field_targets(field_path)
        values = {target: row[_column_alias(target)] for target in targets}
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(resulting_review_version),0) AS review_version "
                "FROM case_import_hcm_correction_events WHERE canonical_review_identity=%s",
                (row["review_identity"],),
            )
            version_row = cursor.fetchone() or {}
        review_version = int(version_row.get("review_version") or 0)
        if resulting_review_version is not None:
            review_version = resulting_review_version
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

    def query_review(self, review_identity: str):
        row = self._load_review_row(review_identity)
        facts = self._facts_from_row(row)
        resolved = not self._unresolved_fields((facts.field_path,), row)
        return {"review_identity": facts.review_identity, "case_no": facts.case_no,
                "source_field": facts.field_path, "review_version": facts.review_version,
                "resolved": resolved}

    def _review_progress(self, review_identity: str, *, for_update: bool = False):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT resulting_review_version,adopted_field_paths FROM case_import_hcm_correction_events "
                "WHERE canonical_review_identity=%s" + (" FOR UPDATE" if for_update else ""),
                (review_identity,),
            )
            events = cursor.fetchall() or ()
        paths = {path for event in events for path in (
            json.loads(event["adopted_field_paths"]) if isinstance(event["adopted_field_paths"], str)
            else event["adopted_field_paths"]
        )}
        skipped = {path.removeprefix(HCM_SKIP_FIELD_PREFIX) for path in paths if path.startswith(HCM_SKIP_FIELD_PREFIX)}
        if HCM_SKIP_REJECT_REASON_PATH in paths:
            skipped.add("不符合原因")
        return {"review_version": max((int(event["resulting_review_version"]) for event in events), default=0),
                "skipped_fields": skipped, "reason_skipped": "不符合原因" in skipped}

    def _unresolved_fields(self, fields, row, *, progress=None):
        unresolved = unresolved_hcm_review_fields(tuple(fields), _current_values(row))
        if not unresolved:
            return ()
        progress = progress if progress is not None else self._review_progress(str(row["review_identity"]))
        return tuple(field for field in unresolved if field not in progress["skipped_fields"])

    def load_skip_facts(self, review_identity: str, *, for_update: bool) -> HcmReviewSkipFacts:
        row = self._load_review_row(review_identity, for_update=for_update)
        progress = self._review_progress(review_identity, for_update=for_update)
        codes = json.loads(row["issue_codes"]) if isinstance(row["issue_codes"], str) else row["issue_codes"]
        fields = tuple(sorted({code.split(":", 1)[1] for code in codes
                               if code.startswith(("hcm_field_missing:", "hcm_field_invalid:"))}))
        return HcmReviewSkipFacts(review_identity, str(row["case_no"]),
                                 int(progress.get("review_version") or 0), str(row["source_fingerprint"]),
                                 tuple(codes), row.get("clients_reject_reason"),
                                 bool(progress.get("reason_skipped")), bool(row["is_current"]),
                                 self._unresolved_fields(fields, row, progress=progress))

    def apply_skip(self, facts, request) -> str:
        row = self._load_review_row(facts.review_identity, for_update=True)
        event_identity = _identity("hcm-review-skip", request.idempotency_key)
        root_fingerprint = hashlib.sha256(_json({"case_no": facts.case_no, "current_values": _current_values(row)}).encode("utf-8")).hexdigest()
        path = HCM_SKIP_REJECT_REASON_PATH if request.source_field is None else hcm_field_skip_path(request.source_field)
        reason = "人工確認略過：缺少不符合原因" if request.source_field is None else "人工確認略過：" + request.source_field
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO case_import_hcm_correction_events "
                "(event_identity,case_no,client_id,review_binding_id,canonical_review_identity,"
                "expected_review_version,resulting_review_version,prior_occurrence_id,source_event_identity,"
                "source_fingerprint,candidate_fingerprint,adopted_field_paths,root_before_fingerprint,"
                "root_after_fingerprint,actor,reason,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (event_identity, facts.case_no, int(row["client_id"]), int(row["binding_id"]),
                 facts.review_identity, facts.review_version, facts.review_version + 1, None,
                 "hcm-review-disposition:" + event_identity, facts.source_fingerprint,
                 request.preview_fingerprint, _json([path]), root_fingerprint,
                 root_fingerprint, request.actor, reason, request.correlation_id),
            )
        return event_identity

    def query_current_reviews(self, *, limit: int, before_id: int | None):
        # Paginate the current owner predicate, never a downloaded first page.
        items = []
        cursor_id = before_id
        while len(items) <= limit:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT r.id,r.review_identity,b.case_no,r.issue_codes,EXISTS(SELECT 1 FROM order_service_data_locks l "
                    "WHERE l.case_no=b.case_no) AS service_data_locked FROM case_import_hcm_review_rows r "
                    "JOIN case_import_hcm_review_case_bindings b ON b.review_row_id=r.id "
                    "WHERE (%s IS NULL OR r.id<%s) AND NOT EXISTS (SELECT 1 "
                    "FROM case_import_hcm_review_rows newer JOIN case_import_hcm_review_case_bindings nb "
                    "ON nb.review_row_id=newer.id WHERE nb.case_no=b.case_no AND newer.id>r.id) "
                    "ORDER BY r.id DESC LIMIT 100", (cursor_id, cursor_id))
                rows = cursor.fetchall()
            if not rows:
                break
            for row in rows:
                cursor_id = int(row["id"])
                codes = json.loads(row["issue_codes"]) if isinstance(row["issue_codes"], str) else row["issue_codes"]
                fields = sorted({code.split(":", 1)[1] for code in codes
                                 if code.startswith(("hcm_field_missing:", "hcm_field_invalid:"))})
                if not fields:
                    continue
                can_correct = False
                unavailable_reason = None
                if len(fields) == 1:
                    try:
                        state = self.query_review(str(row["review_identity"]))
                        if state["resolved"]:
                            continue
                        targets = hcm_field_targets(fields[0])
                        locked = bool(row.get("service_data_locked")) and any(target.startswith("orders.") for target in targets)
                        can_correct = not locked and fields[0] != "不符合原因"
                        unavailable_reason = "service_data_locked" if locked else None
                    except ValueError as error:
                        if str(error) not in {"hcm_resubmission_review_scope_ambiguous", "hcm_resubmission_field_not_owned", "hcm_resubmission_not_available"}:
                            raise
                        if str(error) != "hcm_resubmission_not_available":
                            current = self._load_review_row(str(row["review_identity"]))
                            fields = list(self._unresolved_fields(fields, current))
                            if not fields:
                                continue
                else:
                    try:
                        current = self._load_review_row(str(row["review_identity"]))
                        fields = list(self._unresolved_fields(fields, current))
                        if not fields:
                            continue
                    except ValueError as error:
                        if str(error) != "hcm_resubmission_not_available":
                            raise
                items.append({"source_id": cursor_id, "review_identity": str(row["review_identity"]),
                              "case_no": str(row["case_no"]), "fields": fields,
                              "can_correct": can_correct, "unavailable_reason": unavailable_reason})
                if len(items) > limit:
                    break
            if len(rows) < 100:
                break
        return {"items": items[:limit], "next_cursor": items[limit-1]["source_id"] if len(items) > limit else None}

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

    def find_receipt(self, idempotency_key: str, *, for_update: bool = False):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM case_import_hcm_correction_receipts WHERE idempotency_key=%s" + (" FOR UPDATE" if for_update else ""),
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
        resulting_review_version = facts.review_version + 1
        after = self.load_facts(candidate.review_identity, for_update=True,
                                resulting_review_version=resulting_review_version)
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


_TARGETS = sorted({target for fields in (
        hcm_field_targets("報名時間(建檔)"), hcm_field_targets("IP位址"), hcm_field_targets("姓名"),
        hcm_field_targets("性別"), hcm_field_targets("行動電話"), hcm_field_targets("縣市"),
        hcm_field_targets("預產期/預計服務開始月份"), hcm_field_targets("居住型態"),
        hcm_field_targets("不符合原因"),
        hcm_field_targets("生產方式"), hcm_field_targets("寶寶資訊"), hcm_field_targets("服務時間"),
        hcm_field_targets("預計服務日期"), hcm_field_targets("希望服務天數"), hcm_field_targets("服務方式"),
    ) for target in fields})
_TARGET_SELECTS = ",".join(
    f"{_table_alias(target)}.{target.split('.', 1)[1]} AS {_column_alias(target)}"
    for target in _TARGETS
)


def _current_values(row) -> dict[str, object]:
    return {target: row.get(_column_alias(target)) for target in _TARGETS}

_FACTS_SQL = (
    "SELECT b.id AS binding_id,b.case_no,e.client_id,r.review_identity,r.issue_codes,r.source_fingerprint,"
    "NOT EXISTS(SELECT 1 FROM case_import_hcm_review_rows newer "
    "JOIN case_import_hcm_review_case_bindings nb ON nb.review_row_id=newer.id "
    "WHERE nb.case_no=b.case_no AND newer.id>r.id) AS is_current,"
    "r.source_event_identity AS prior_source_event_identity,c.client_hcm_correction_version,"
    "ord.lifecycle_version AS order_version," + _TARGET_SELECTS + " FROM case_import_hcm_review_rows r "
    "JOIN case_import_hcm_review_case_bindings b ON b.review_row_id=r.id "
    "JOIN case_import_events e ON e.id=b.root_import_event_id AND e.case_no=b.case_no "
    "JOIN clients c ON c.id=e.client_id AND c.case_no=b.case_no "
    "JOIN orders ord ON ord.case_no=b.case_no WHERE r.review_identity=%s"
)

__all__ = ["MySqlHcmResubmissionRepository"]

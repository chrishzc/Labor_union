"""
File: historical_order_adoption_repository.py
Description: 鎖定歷史案件並原子保存 Orders event、配對證據、review、outbox 與 receipt。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import json
from uuid import uuid4

from domains.orders.historical_adoption import HistoricalOrderCurrentFacts, HistoricalOrderOutcome
from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionReceipt,
    HistoricalOrderAdoptionRequest,
    HistoricalOrderAdoptionPreview,
    HistoricalPairingResolution,
)


class MySqlHistoricalOrderAdoptionRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load_order(self, case_no, client_name, *, for_update):
        del client_name
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT o.case_no,o.status,o.lifecycle_version,o.start_date,"
                "o.actual_start_date,o.actual_end_date,c.name "
                "FROM orders o JOIN clients c ON c.id=o.client_id "
                "WHERE o.case_no=%s" + suffix,
                (case_no,),
            )
            rows = cursor.fetchall()
        if len(rows) != 1:
            return None
        row = rows[0]
        return HistoricalOrderCurrentFacts(
            str(row["case_no"]),
            str(row["name"]),
            OrderLifecycleStatus(str(row["status"])),
            int(row["lifecycle_version"]),
            _optional_date(row.get("start_date")),
            _optional_date(row.get("actual_start_date")),
            _optional_date(row.get("actual_end_date")),
        )

    def resolve_staff(self, name, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute("SELECT id FROM staff WHERE name=%s ORDER BY id" + suffix, (name,))
            return tuple(int(row["id"]) for row in cursor.fetchall())

    def active_assignments(self, case_no, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT id,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status,generation_id "
                "FROM case_staff_assignments WHERE case_no=%s AND status<>'cancelled' "
                "ORDER BY assignment_sequence,id" + suffix,
                (case_no,),
            )
            return tuple(cursor.fetchall())

    def find_receipt(self, key, source_identity):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT command_fingerprint,outcome,case_no,resulting_version,assignment_count,"
                "review_identity,preview_fingerprint FROM historical_order_adoption_receipts "
                "WHERE idempotency_key=%s OR source_event_identity=%s ORDER BY id LIMIT 1 FOR UPDATE",
                (key, source_identity),
            )
            return cursor.fetchone()

    def persist(self, request, preview, assignment_ids):
        command_fingerprint = _command_fingerprint(request)
        review_identity = self._append_review(request, preview)
        lifecycle_event_id = self._apply_order(request, preview)
        receipt_id = self._append_receipt(
            request,
            preview,
            command_fingerprint,
            lifecycle_event_id,
            len(assignment_ids),
            review_identity,
        )
        self._append_pairing_evidence(receipt_id, preview, assignment_ids)
        self._append_outbox(receipt_id, request, preview, review_identity)
        return HistoricalOrderAdoptionReceipt(
            preview.outcome,
            preview.case_no,
            preview.resulting_version,
            len(assignment_ids),
            review_identity,
            False,
            preview.fingerprint,
        )

    def _append_review(self, request, preview):
        if preview.outcome is HistoricalOrderOutcome.UNMATCHED_CASE or not preview.issue_codes:
            return None
        review_identity = f"historical-order-review:{uuid4()}"
        evidence = {
            "source_row": request.row.source_row,
            "case_identity": _mask_case(preview.case_no),
            "outcome": preview.outcome.value,
            "pairing_resolutions": tuple(item.resolution.value for item in preview.pairings),
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_order_adoption_reviews "
                "(review_identity,source_event_identity,source_fingerprint,masked_case_identity,"
                "issue_codes,evidence_snapshot) VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    review_identity,
                    request.row.source_identity,
                    request.row.source_fingerprint,
                    _mask_case(preview.case_no),
                    _json(preview.issue_codes),
                    _json(evidence),
                ),
            )
        return review_identity

    def _apply_order(self, request, preview):
        if (
            preview.outcome is not HistoricalOrderOutcome.ADOPTED
            or preview.resulting_version == preview.expected_version
        ):
            return None
        actual_start_present, actual_start_date = _date_patch_value(
            preview.date_patch, "actual_start_date"
        )
        actual_end_present, actual_end_date = _date_patch_value(
            preview.date_patch, "actual_end_date"
        )
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "UPDATE orders SET status=%s,lifecycle_version=%s,"
                "actual_start_date=CASE WHEN %s THEN %s ELSE actual_start_date END,"
                "actual_end_date=CASE WHEN %s THEN %s ELSE actual_end_date END "
                "WHERE case_no=%s AND lifecycle_version=%s",
                (
                    preview.after_status,
                    preview.resulting_version,
                    actual_start_present,
                    actual_start_date,
                    actual_end_present,
                    actual_end_date,
                    preview.case_no,
                    preview.expected_version,
                ),
            )
            if int(cursor.rowcount) != 1:
                raise RuntimeError("historical_order_candidate_stale")
            cursor.execute(
                "INSERT INTO order_lifecycle_state_events "
                "(case_no,trigger_event,before_status,after_status,actor,business_date,"
                "expected_version,idempotency_key,facts_snapshot) "
                "SELECT case_no,'historical_order_adoption',%s,%s,%s,CURRENT_DATE,%s,%s,%s "
                "FROM orders WHERE case_no=%s",
                (
                    preview.before_status,
                    preview.after_status,
                    request.actor,
                    preview.expected_version,
                    request.idempotency_key,
                    _json(_event_snapshot(request, preview)),
                    preview.case_no,
                ),
            )
            return int(cursor.lastrowid)

    def _append_receipt(self, request, preview, command_fingerprint, event_id, assignment_count, review_identity):
        snapshot = {
            "outcome": preview.outcome.value,
            "result": preview.result.value,
            "issue_codes": preview.issue_codes,
            "service_calendar_status": "not_reconstructed_for_historical_order",
            "historical_service_days_status": (
                "pending_operator_confirmation"
                if preview.result.value == "historical_service_completed"
                else "not_yet_eligible"
            ),
            "payroll_rebuild_status": "not_started",
            **_operational_baseline_snapshot(request, preview),
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_order_adoption_receipts "
                "(idempotency_key,command_fingerprint,source_event_identity,source_fingerprint,"
                "preview_fingerprint,case_no,outcome,expected_version,resulting_version,"
                "lifecycle_event_id,assignment_count,review_identity,result_snapshot,actor,reason,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    request.idempotency_key,
                    command_fingerprint,
                    request.row.source_identity,
                    request.row.source_fingerprint,
                    preview.fingerprint.value,
                    preview.case_no,
                    preview.outcome.value,
                    preview.expected_version,
                    preview.resulting_version,
                    event_id,
                    assignment_count,
                    review_identity,
                    _json(snapshot),
                    request.actor,
                    request.reason,
                    request.correlation_id,
                ),
            )
            return int(cursor.lastrowid)

    def _append_pairing_evidence(self, receipt_id, preview, assignment_ids):
        assignment_iterator = iter(assignment_ids)
        rows = []
        for item in preview.pairings:
            assignment_id = (
                next(assignment_iterator)
                if item.resolution is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE
                else item.assignment_id
            )
            rows.append((
                receipt_id,
                item.ordinal,
                item.masked_name,
                item.staff_id,
                item.resolution.value,
                item.start_date,
                item.end_date,
                assignment_id,
                _json(item.issue_codes),
            ))
        if rows:
            with _cursor(self._connection) as cursor:
                cursor.executemany(
                    "INSERT INTO historical_order_pairing_evidence "
                    "(receipt_id,caregiver_ordinal,masked_staff_name,staff_id,resolution,source_start_date,"
                    "source_end_date,assignment_id,issue_codes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    rows,
                )

    def _append_outbox(self, receipt_id, request, preview, review_identity):
        if preview.outcome is HistoricalOrderOutcome.UNMATCHED_CASE:
            return
        payload = {
            "case_no": preview.case_no,
            "outcome": preview.outcome.value,
            "result": preview.result.value,
            "review_identity": review_identity,
            "issue_codes": preview.issue_codes,
        }
        with _cursor(self._connection) as cursor:
            if preview.outcome is HistoricalOrderOutcome.ADOPTED:
                _insert_outbox(cursor, receipt_id, request.idempotency_key, "historical_order_adopted", payload)
            if review_identity:
                _insert_outbox(cursor, receipt_id, request.idempotency_key, "historical_order_review_required", payload)


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _command_fingerprint(request):
    return fingerprint_payload({
        "source_identity": request.row.source_identity,
        "source_fingerprint": request.row.source_fingerprint,
    }).value


def _date_patch_value(date_patch, field_name):
    for field, value in date_patch:
        if field == field_name:
            return True, value
    return False, None


def _insert_outbox(cursor, receipt_id, key, intent_type, payload):
    cursor.execute(
        "INSERT INTO historical_order_adoption_outbox "
        "(receipt_id,intent_key,intent_type,bounded_snapshot) VALUES (%s,%s,%s,%s)",
        (receipt_id, f"{key}:{intent_type}", intent_type, _json(payload)),
    )


def _event_snapshot(request, preview):
    return {
        "lifecycle_origin": "historical_assertion",
        "source_identity": request.row.source_identity,
        "source_fingerprint": request.row.source_fingerprint,
        "resulting_version": preview.resulting_version,
        "date_patch": tuple(
            (field, value.isoformat() if value is not None else None)
            for field, value in preview.date_patch
        ),
        "issue_codes": preview.issue_codes,
        "side_effects_suppressed": True,
    }


def _operational_baseline_snapshot(request, preview):
    source_status = getattr(request.row.asserted_status, "value", None)
    step, actual_start = _operational_baseline_step(preview)
    return {
        "historical_source_status": source_status,
        "operational_baseline_step": step,
        "operational_baseline_actual_start_date": (
            actual_start.isoformat() if actual_start is not None else None
        ),
    }


def _operational_baseline_step(preview):
    if preview.outcome is not HistoricalOrderOutcome.ADOPTED:
        return None, None
    status = OrderLifecycleStatus(str(preview.after_status))
    date_patch = dict(preview.date_patch)
    actual_start = date_patch.get("actual_start_date")
    if status is OrderLifecycleStatus.CANCELLED:
        return None, None
    if status in {
        OrderLifecycleStatus.COMPLETED,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }:
        return 11, _optional_date(actual_start)
    if status in {
        OrderLifecycleStatus.IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
    }:
        return 10, _optional_date(actual_start)
    if actual_start is not None and status in {
        OrderLifecycleStatus.DISCUSSION,
        OrderLifecycleStatus.ESTABLISHED,
    }:
        return 10, _optional_date(actual_start)
    if status in {
        OrderLifecycleStatus.ESTABLISHED,
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
    }:
        return 9, None
    return None, None


def _optional_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _optional_int(value):
    return None if value is None else int(value)


def _mask_case(case_no):
    text = str(case_no or "").strip()
    return text[:2] + "*" * max(0, len(text) - 4) + text[-2:] if len(text) > 4 else "*" * len(text)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = ["MySqlHistoricalOrderAdoptionRepository"]

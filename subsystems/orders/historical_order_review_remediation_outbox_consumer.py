"""
File: historical_order_review_remediation_outbox_consumer.py
Description: 消費 Orders immutable remediation outbox，保留 canonical receipt 與 bounded retry。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import date, datetime

from pymysql.err import OperationalError

from subsystems.orders.historical_order_outbox_retry import (
    HISTORICAL_ORDER_OUTBOX_MAX_ATTEMPTS,
    HISTORICAL_ORDER_OUTBOX_RETRY_DELAY_SECONDS,
    HISTORICAL_ORDER_OUTBOX_RETRY_READY_SQL,
    HistoricalOrderOutboxRuntime,
    historical_order_outbox_error_code,
    require_historical_order_outbox_runtime,
)


@dataclass(frozen=True, slots=True)
class HistoricalOrderReviewRemediationOutboxResult:
    delivered_count: int
    failed_count: int


def consume_historical_order_review_remediation_events(
    connection,
    *,
    maximum_events: int = 50,
    runtime: HistoricalOrderOutboxRuntime | None = None,
) -> HistoricalOrderReviewRemediationOutboxResult:
    """Consume committed Orders remediation events with a bounded retry ceiling."""
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    runtime = require_historical_order_outbox_runtime(runtime)
    delivered = failed = 0
    for _ in range(maximum_events):
        outcome = _consume_next(connection, runtime)
        if outcome is None:
            break
        delivered += int(outcome)
        failed += int(not outcome)
        if not outcome:
            break
    return HistoricalOrderReviewRemediationOutboxResult(delivered, failed)


def _consume_next(connection, runtime: HistoricalOrderOutboxRuntime):
    event = None
    try:
        event = _claim_next(connection)
        if event is None:
            connection.rollback()
            return None
        disposition = _load_disposition(connection, int(event["event_id"]))
        prior = _load_review(connection, disposition["prior_review_identity"])
        original = _load_receipt(connection, int(disposition["original_adoption_receipt_id"]))
        replacement = _load_receipt(
            connection, int(disposition["replacement_adoption_receipt_id"])
        )
        remediation_receipt = _load_remediation_receipt(
            connection, int(event["remediation_receipt_id"])
        )
        _validate_disposition(
            event,
            disposition,
            remediation_receipt,
            prior,
            original,
            replacement,
        )
        orders_terminal_snapshot = _orders_snapshot_from_disposition(
            event, disposition
        )
        _assert_orders_terminal_snapshot(
            connection, original["case_no"], orders_terminal_snapshot
        )

        successor = None
        if disposition["disposition"] == "superseded_by_replacement_review":
            successor = _load_review(connection, disposition["successor_review_identity"])
            _validate_successor(disposition, replacement, successor, prior)

        _mark_delivered(connection, int(event["id"]))
        connection.commit()
        return True
    except OperationalError as error:
        connection.rollback()
        _record_failure(connection, event, error, runtime)
        return False
    except Exception as error:
        connection.rollback()
        _record_failure(connection, event, error, runtime)
        return False


def _claim_next(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,event_id,remediation_receipt_id,bounded_snapshot "
            "FROM historical_order_review_remediation_outbox "
            "WHERE intent_type='historical_order_review_remediated' AND published_at IS NULL "
            f"AND attempts<{HISTORICAL_ORDER_OUTBOX_MAX_ATTEMPTS} "
            f"AND {HISTORICAL_ORDER_OUTBOX_RETRY_READY_SQL} "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _load_disposition(connection, event_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,event_identity,prior_review_identity,original_adoption_receipt_id,"
            "replacement_adoption_receipt_id,disposition,successor_review_identity,"
            "source_content_digest,review_fingerprint,command_fingerprint,actor,reason,"
            "evidence_snapshot,correlation_id FROM historical_order_review_remediation_events "
            "WHERE id=%s FOR UPDATE",
            (event_id,),
        )
        value = cursor.fetchone()
    if not isinstance(value, dict):
        raise ValueError("historical_order_remediation_event_missing")
    return value


def _load_review(connection, review_identity):
    if not isinstance(review_identity, str) or not review_identity.strip():
        raise ValueError("historical_order_review_identity_missing")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT review_identity,source_event_identity,source_fingerprint,"
            "masked_case_identity,issue_codes,evidence_snapshot FROM "
            "historical_order_adoption_reviews WHERE review_identity=%s FOR UPDATE",
            (review_identity,),
        )
        value = cursor.fetchone()
    if not isinstance(value, dict):
        raise ValueError("historical_order_review_root_missing")
    return value


def _load_receipt(connection, receipt_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,source_event_identity,source_fingerprint,preview_fingerprint,"
            "case_no,outcome,review_identity,result_snapshot FROM "
            "historical_order_adoption_receipts WHERE id=%s FOR UPDATE",
            (receipt_id,),
        )
        value = cursor.fetchone()
    if not isinstance(value, dict):
        raise ValueError("historical_order_adoption_receipt_missing")
    return value


def _load_remediation_receipt(connection, receipt_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,event_id,command_fingerprint,preview_fingerprint,"
            "expected_remediation_version,resulting_remediation_version,result_snapshot "
            "FROM historical_order_review_remediation_receipts WHERE id=%s FOR UPDATE",
            (receipt_id,),
        )
        value = cursor.fetchone()
    if not isinstance(value, dict):
        raise ValueError("historical_order_remediation_receipt_missing")
    return value


def _validate_disposition(
    event, disposition, remediation_receipt, prior, original, replacement
) -> None:
    snapshot = _json_object(event.get("bounded_snapshot"))
    if snapshot.get("event_id") is not None and int(snapshot["event_id"]) != int(disposition["id"]):
        raise ValueError("historical_order_remediation_event_binding_mismatch")
    if snapshot.get("prior_review_identity") not in (None, disposition["prior_review_identity"]):
        raise ValueError("historical_order_remediation_prior_binding_mismatch")
    if int(remediation_receipt["id"]) != int(event["remediation_receipt_id"]):
        raise ValueError("historical_order_remediation_receipt_binding_mismatch")
    if int(remediation_receipt["event_id"]) != int(disposition["id"]):
        raise ValueError("historical_order_remediation_receipt_event_mismatch")
    if remediation_receipt["command_fingerprint"] != disposition["command_fingerprint"]:
        raise ValueError("historical_order_remediation_command_fingerprint_mismatch")
    if int(remediation_receipt["expected_remediation_version"]) != 0 or int(
        remediation_receipt["resulting_remediation_version"]
    ) != 1:
        raise ValueError("historical_order_remediation_receipt_version_mismatch")
    _json_object(remediation_receipt["result_snapshot"])
    if disposition["original_adoption_receipt_id"] == disposition["replacement_adoption_receipt_id"]:
        raise ValueError("historical_order_remediation_receipt_not_replaced")
    if prior["review_identity"] != disposition["prior_review_identity"]:
        raise ValueError("historical_order_remediation_prior_binding_mismatch")
    if original["id"] != disposition["original_adoption_receipt_id"] or original.get("review_identity") != prior["review_identity"]:
        raise ValueError("historical_order_remediation_original_receipt_mismatch")
    if replacement["id"] != disposition["replacement_adoption_receipt_id"]:
        raise ValueError("historical_order_remediation_replacement_receipt_mismatch")
    for key in ("source_content_digest", "review_fingerprint", "command_fingerprint"):
        if _hex_digest(disposition.get(key)) is None:
            raise ValueError("historical_order_remediation_fingerprint_invalid")
    if not isinstance(disposition.get("actor"), str) or not disposition["actor"].strip():
        raise ValueError("historical_order_remediation_actor_missing")
    if not isinstance(disposition.get("reason"), str) or not disposition["reason"].strip():
        raise ValueError("historical_order_remediation_reason_missing")
    if not isinstance(disposition.get("correlation_id"), str) or not disposition["correlation_id"].strip():
        raise ValueError("historical_order_remediation_correlation_missing")
    evidence = _json_object(disposition.get("evidence_snapshot"))
    evidence_items = evidence.get("evidence")
    if not isinstance(evidence_items, list) or not evidence_items or not all(
        isinstance(item, str) and item.strip() for item in evidence_items
    ):
        raise ValueError("historical_order_remediation_evidence_missing")
    bounded_orders_snapshot = _orders_snapshot_from_payload(snapshot)
    evidence_orders_snapshot = _orders_snapshot_from_payload(evidence)
    if bounded_orders_snapshot != evidence_orders_snapshot:
        raise ValueError("historical_order_remediation_orders_snapshot_mismatch")
    if original.get("case_no") != replacement.get("case_no"):
        raise ValueError("historical_order_remediation_case_binding_mismatch")
    if bounded_orders_snapshot["case_no"] != original.get("case_no"):
        raise ValueError("historical_order_remediation_case_binding_mismatch")
    if disposition["disposition"] not in {
        "corrected_source_adopted",
        "superseded_by_replacement_review",
    }:
        raise ValueError("historical_order_remediation_disposition_invalid")
    if disposition["disposition"] == "corrected_source_adopted":
        if disposition.get("successor_review_identity") is not None:
            raise ValueError("historical_order_remediation_successor_unexpected")
        if replacement.get("outcome") != "adopted" or replacement.get("review_identity") is not None:
            raise ValueError("historical_order_remediation_clean_replacement_invalid")
        if _text_tuple(_json_object(replacement.get("result_snapshot")).get("issue_codes", [])):
            raise ValueError("historical_order_remediation_clean_replacement_has_issue_codes")
    elif not disposition.get("successor_review_identity"):
        raise ValueError("historical_order_remediation_successor_missing")


def _validate_successor(disposition, replacement, successor, prior) -> None:
    identity = disposition.get("successor_review_identity")
    if not isinstance(identity, str) or not identity.strip() or identity == prior["review_identity"]:
        raise ValueError("historical_order_remediation_successor_invalid")
    if successor["review_identity"] != identity:
        raise ValueError("historical_order_remediation_successor_binding_mismatch")
    if replacement.get("review_identity") != identity:
        raise ValueError("historical_order_remediation_successor_receipt_mismatch")
    if replacement.get("outcome") not in {"review_required", "current_conflict"}:
        raise ValueError("historical_order_remediation_successor_outcome_invalid")
    if not _text_tuple(successor.get("issue_codes")):
        raise ValueError("historical_order_remediation_successor_issue_codes_missing")


def _orders_snapshot_from_disposition(event, disposition) -> dict[str, object]:
    bounded = _orders_snapshot_from_payload(_json_object(event.get("bounded_snapshot")))
    evidence = _orders_snapshot_from_payload(
        _json_object(disposition.get("evidence_snapshot"))
    )
    if bounded != evidence:
        raise ValueError("historical_order_remediation_orders_snapshot_mismatch")
    return bounded


def _assert_orders_terminal_snapshot(
    connection, case_no: str, expected: dict[str, object]
) -> None:
    current = _load_orders_terminal_snapshot(connection, case_no)
    if current != expected:
        raise RuntimeError("historical_order_remediation_orders_root_stale")


def _load_orders_terminal_snapshot(connection, case_no: str) -> dict[str, object]:
    if not isinstance(case_no, str) or not case_no.strip():
        raise ValueError("historical_order_remediation_case_binding_missing")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT case_no,status,lifecycle_version,actual_start_date,actual_end_date "
            "FROM orders WHERE case_no=%s FOR UPDATE",
            (case_no,),
        )
        order = cursor.fetchone()
        if not isinstance(order, dict):
            raise ValueError("historical_order_remediation_order_root_missing")
        cursor.execute(
            "SELECT id AS assignment_id,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status "
            "FROM case_staff_assignments WHERE case_no=%s AND status<>'cancelled' "
            "ORDER BY assignment_sequence,id FOR UPDATE",
            (case_no,),
        )
        assignments = cursor.fetchall()
    return _canonical_orders_snapshot(order, assignments, case_no)


def _orders_snapshot_from_payload(payload) -> dict[str, object]:
    value = _json_object(payload).get("orders_terminal_snapshot")
    if not isinstance(value, dict):
        raise ValueError("historical_order_remediation_orders_snapshot_missing")
    return _canonical_orders_snapshot(value, value.get("active_assignments"), value.get("case_no"), payload=True)


def _canonical_orders_snapshot(
    order, assignments, case_no, *, payload: bool = False
) -> dict[str, object]:
    if not isinstance(order, dict) or not isinstance(case_no, str) or not case_no.strip():
        raise ValueError("historical_order_remediation_order_root_malformed")
    expected_order_keys = {"case_no", "status", "lifecycle_version", "actual_start_date", "actual_end_date"}
    if payload and set(order) != (expected_order_keys | {"active_assignments"}):
        raise ValueError("historical_order_remediation_orders_snapshot_malformed")
    if order.get("case_no") != case_no:
        raise ValueError("historical_order_remediation_case_binding_mismatch")
    status = order.get("status")
    version = order.get("lifecycle_version")
    if not isinstance(status, str) or not status.strip() or isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise ValueError("historical_order_remediation_order_root_malformed")
    start = _snapshot_date(order.get("actual_start_date"), "actual_start_date")
    end = _snapshot_date(order.get("actual_end_date"), "actual_end_date")
    if not isinstance(assignments, (list, tuple)):
        raise ValueError("historical_order_remediation_assignments_malformed")
    normalized = []
    seen_ids = set()
    required_assignment_keys = {
        "assignment_id", "staff_id", "assignment_sequence", "assigned_start_date",
        "assigned_end_date", "status",
    }
    for assignment in assignments:
        if not isinstance(assignment, dict) or set(assignment) != required_assignment_keys:
            raise ValueError("historical_order_remediation_assignment_malformed")
        assignment_id = assignment.get("assignment_id")
        staff_id = assignment.get("staff_id")
        sequence = assignment.get("assignment_sequence")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (assignment_id, staff_id, sequence)):
            raise ValueError("historical_order_remediation_assignment_malformed")
        if assignment_id in seen_ids:
            raise ValueError("historical_order_remediation_assignment_duplicate")
        seen_ids.add(assignment_id)
        assignment_status = assignment.get("status")
        if not isinstance(assignment_status, str) or not assignment_status.strip():
            raise ValueError("historical_order_remediation_assignment_malformed")
        normalized.append({
            "assignment_id": assignment_id,
            "staff_id": staff_id,
            "assignment_sequence": sequence,
            "assigned_start_date": _snapshot_date(assignment.get("assigned_start_date"), "assigned_start_date"),
            "assigned_end_date": _snapshot_date(assignment.get("assigned_end_date"), "assigned_end_date"),
            "status": assignment_status,
        })
    return {
        "case_no": case_no,
        "status": status,
        "lifecycle_version": version,
        "actual_start_date": start,
        "actual_end_date": end,
        "active_assignments": normalized,
    }


def _snapshot_date(value, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        try:
            datetime.fromisoformat(value)
        except ValueError:
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise ValueError(
                    f"historical_order_remediation_{field}_malformed"
                ) from error
        return value
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    raise ValueError(f"historical_order_remediation_{field}_malformed")


def _mark_delivered(connection, event_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE historical_order_review_remediation_outbox SET published_at=CURRENT_TIMESTAMP,"
            "last_error=NULL WHERE id=%s AND published_at IS NULL",
            (event_id,),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("historical_order_review_remediation_outbox_delivery_conflict")


def _mark_failed(connection, event, error: Exception) -> None:
    if not isinstance(event, dict) or "id" not in event:
        return
    with connection.cursor() as cursor:
        message = historical_order_outbox_error_code(error)
        cursor.execute(
            "UPDATE historical_order_review_remediation_outbox SET attempts=attempts+1,"
            "last_error=JSON_OBJECT('error_code',%s,'retry_after_epoch',"
            f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {HISTORICAL_ORDER_OUTBOX_RETRY_DELAY_SECONDS} SECOND)),"
            f"'terminal',attempts+1>={HISTORICAL_ORDER_OUTBOX_MAX_ATTEMPTS}) WHERE id=%s",
            (message, int(event["id"])),
        )


def _record_failure(
    connection,
    event,
    error: Exception,
    runtime: HistoricalOrderOutboxRuntime,
) -> None:
    if not isinstance(event, dict) or "id" not in event:
        return None
    with runtime.failure_unit_of_work(connection) as unit_of_work:
        _mark_failed(connection, event, error)
        unit_of_work.commit()


def _json_object(value) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("historical_order_remediation_payload_not_object")
    return parsed


def _text_tuple(value) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("historical_order_review_issue_codes_not_array")
    return tuple(sorted({str(item) for item in parsed}))


def _hex_digest(value) -> str | None:
    if not isinstance(value, str) or len(value) != 64:
        return None
    return value if all(char in "0123456789abcdef" for char in value) else None


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


__all__ = [
    "HistoricalOrderReviewRemediationOutboxResult",
    "consume_historical_order_review_remediation_events",
]

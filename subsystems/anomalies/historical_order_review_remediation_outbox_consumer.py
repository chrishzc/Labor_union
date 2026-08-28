"""
File: historical_order_review_remediation_outbox_consumer.py
Description: 以 Orders immutable remediation disposition 重投影歷史訂單警示。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from datetime import date, datetime

from pymysql.err import OperationalError

from domains.anomalies.registry import DesiredAlertState, default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest
from subsystems.anomalies.historical_order_adoption_outbox_consumer import (
    append_historical_order_warning_occurrence,
)
from subsystems.anomalies.import_warning_projection_retry import (
    MAX_WARNING_PROJECTION_ATTEMPTS,
    WARNING_PROJECTION_RETRY_DELAY_SECONDS,
    WARNING_PROJECTION_RETRY_READY_SQL,
    warning_projection_error_code,
)
from domains.orders.historical_order_warning_review import (
    build_historical_order_warning_occurrences,
)


@dataclass(frozen=True, slots=True)
class HistoricalOrderReviewRemediationOutboxResult:
    delivered_count: int
    failed_count: int


class BorrowedUnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def consume_historical_order_review_remediation_events(
    connection, *, maximum_events: int = 50
) -> HistoricalOrderReviewRemediationOutboxResult:
    """Consume committed Orders remediation events with a bounded retry ceiling."""
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        outcome = _consume_next(connection)
        if outcome is None:
            break
        delivered += int(outcome)
        failed += int(not outcome)
        if not outcome:
            break
    return HistoricalOrderReviewRemediationOutboxResult(delivered, failed)


def _consume_next(connection):
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
            _project_successor(connection, event, successor)

        _close_prior_warnings(connection, prior, successor)
        _project_prior_inactive(connection, event, prior)
        _assert_readback(connection, prior, successor)
        _mark_delivered(connection, int(event["id"]))
        connection.commit()
        return True
    except OperationalError as error:
        connection.rollback()
        _mark_failed(connection, event, error)
        return False
    except Exception as error:
        connection.rollback()
        _mark_failed(connection, event, error)
        return False


def _claim_next(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,event_id,remediation_receipt_id,bounded_snapshot "
            "FROM historical_order_review_remediation_outbox "
            "WHERE intent_type='historical_order_review_remediated' AND published_at IS NULL "
            f"AND attempts<{MAX_WARNING_PROJECTION_ATTEMPTS} "
            f"AND {WARNING_PROJECTION_RETRY_READY_SQL} "
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
            raise ValueError("historical_order_remediation_clean_replacement_has_warnings")
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
        raise ValueError("historical_order_remediation_successor_warnings_missing")


def _project_successor(connection, event, successor) -> None:
    warnings = build_historical_order_warning_occurrences(
        source_event_identity=str(successor["source_event_identity"]),
        masked_case_identity=str(successor["masked_case_identity"]),
        issue_codes=_text_tuple(successor["issue_codes"]),
    )
    if not warnings:
        raise ValueError("historical_order_remediation_successor_warnings_missing")
    for warning in warnings:
        append_historical_order_warning_occurrence(
            connection,
            warning,
            str(successor["review_identity"]),
            _json_object(successor["evidence_snapshot"]),
        )
    application = AnomalyApplication(
        default_anomaly_registry(), MySqlAnomalyRepository(connection), BorrowedUnitOfWork
    )
    application.project(_project_request(event, successor, active=True))


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


def _close_prior_warnings(connection, prior, successor) -> None:
    rows = _load_warning_rows(connection, str(prior["review_identity"]))
    successor_rows = (
        _load_warning_rows(connection, str(successor["review_identity"])) if successor else ()
    )
    by_field = {(str(row["logical_code"]), str(row["field_path"])): row for row in successor_rows}
    for row in rows:
        status = str(row["tracking_status"])
        if status in {"closed", "auto_resolved"}:
            continue
        replacement = None
        if successor is not None:
            replacement = by_field.get(
                (str(row["logical_code"]), str(row["field_path"]))
            )
        _append_warning_close(connection, row, replacement)


def _load_warning_rows(connection, review_identity: str):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT o.id,o.occurrence_identity,o.logical_code,o.field_path,"
            "t.tracking_status,t.tracking_version FROM import_warning_occurrences o "
            "JOIN import_warning_current_tasks t ON t.occurrence_id=o.id "
            "WHERE o.source_receipt_identity=%s AND o.owning_lane='historical_order' "
            "FOR UPDATE",
            (review_identity,),
        )
        return tuple(cursor.fetchall())


def _append_warning_close(connection, row, replacement) -> None:
    occurrence_id = int(row["id"])
    expected = int(row["tracking_version"])
    occurrence_identity = str(row["occurrence_identity"])
    owner_key = f"historical-order-remediation:{occurrence_identity}"
    event_identity = _identity("historical-order-warning-remediation", owner_key)
    fingerprint = _identity("historical-order-warning-remediation-fingerprint", f"{owner_key}:{expected}")
    correlation_id = _identity("historical-order-warning-remediation-correlation", owner_key)
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO import_warning_tracking_events "
            "(event_identity,occurrence_id,action,before_status,after_status,expected_version,"
            "resulting_version,actor_kind,actor_identity,reason_code,command_fingerprint,"
            "idempotency_key,correlation_id) VALUES (%s,%s,'auto_resolved',%s,'auto_resolved',"
            "%s,%s,'system','historical-order-remediation','owner_disposition_applied',%s,%s,%s)",
            (event_identity, occurrence_id, str(row["tracking_status"]), expected, expected + 1, fingerprint, event_identity, correlation_id),
        )
        event_id = int(cursor.lastrowid or 0)
        if event_id <= 0:
            raise RuntimeError("historical_order_remediation_warning_event_missing")
        replacement_id = None if replacement is None else int(replacement["id"])
        cursor.execute(
            "UPDATE import_warning_current_tasks SET tracking_status='auto_resolved',"
            "tracking_version=%s,last_event_id=%s,replacement_occurrence_id=%s,"
            "last_event_at=CURRENT_TIMESTAMP WHERE occurrence_id=%s AND tracking_version=%s",
            (expected + 1, event_id, replacement_id, occurrence_id, expected),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("historical_order_remediation_warning_version_conflict")
        cursor.execute(
            "INSERT INTO import_warning_tracking_receipts "
            "(idempotency_key,command_fingerprint,occurrence_id,tracking_event_id,"
            "expected_version,resulting_version,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (event_identity, fingerprint, occurrence_id, event_id, expected, expected + 1,
             _json({"occurrence_identity": occurrence_identity, "after_status": "auto_resolved", "replacement_occurrence_id": replacement_id})),
        )
        cursor.execute(
            "INSERT INTO import_warning_tracking_outbox (tracking_event_id,intent_key,bounded_snapshot) VALUES (%s,%s,%s)",
            (event_id, _identity("historical-order-warning-remediation-outbox", event_identity),
             _json({"occurrence_identity": occurrence_identity, "tracking_status": "auto_resolved", "tracking_version": expected + 1})),
        )


def _project_prior_inactive(connection, event, prior) -> None:
    application = AnomalyApplication(
        default_anomaly_registry(), MySqlAnomalyRepository(connection), BorrowedUnitOfWork
    )
    application.project(_project_request(event, prior, active=False))


def _project_request(event, review, *, active: bool) -> ProjectAlertRequest:
    identity = str(review["review_identity"])
    return ProjectAlertRequest(
        desired=DesiredAlertState(
            definition_code="HISTORICAL-ORDER-001",
            source_identity=identity,
            source_version=0,
            active=active,
            fingerprint_values={"review_identity": identity},
        ),
        source_event_identity=f"historical-order-review-remediation-outbox:{event['id']}",
        consumer_identity="historical-order-review-remediation-projector-v1",
        partition_identity=f"HISTORICAL-ORDER-001:{identity}",
        display_snapshot={
            "review_identity": identity,
            "masked_case_identity": str(review["masked_case_identity"]),
            "issue_codes": _text_tuple(review["issue_codes"]),
        },
    )


def _assert_readback(connection, prior, successor) -> None:
    _assert_alert(connection, str(prior["review_identity"]), active=False)
    if successor is not None:
        _assert_alert(connection, str(successor["review_identity"]), active=True)
        rows = _load_warning_rows(connection, str(successor["review_identity"]))
        if not rows or any(str(row["tracking_status"]) in {"closed", "auto_resolved"} for row in rows):
            raise RuntimeError("historical_order_remediation_successor_warning_readback_failed")


def _assert_alert(connection, review_identity: str, *, active: bool) -> None:
    fingerprint = default_anomaly_registry().fingerprint(
        DesiredAlertState(
            definition_code="HISTORICAL-ORDER-001",
            source_identity=review_identity,
            source_version=0,
            active=active,
            fingerprint_values={"review_identity": review_identity},
        )
    ).value
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT predicate_active,workflow_status FROM anomaly_current_alerts WHERE fingerprint=%s",
            (fingerprint,),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError(
            "historical_order_remediation_alert_readback_unavailable"
        )
    if not active:
        if int(row["predicate_active"]) != 0 or str(row["workflow_status"]) != "resolved":
            raise RuntimeError("historical_order_remediation_prior_alert_readback_failed")
    elif not isinstance(row, dict) or int(row["predicate_active"]) != 1 or str(row["workflow_status"]) == "resolved":
        raise RuntimeError("historical_order_remediation_successor_alert_readback_failed")


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
        message = warning_projection_error_code(error, owning_lane="historical_order")
        cursor.execute(
            "UPDATE historical_order_review_remediation_outbox SET attempts=attempts+1,"
            "last_error=JSON_OBJECT('error_code',%s,'retry_after_epoch',"
            f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {WARNING_PROJECTION_RETRY_DELAY_SECONDS} SECOND)),"
            f"'terminal',attempts+1>={MAX_WARNING_PROJECTION_ATTEMPTS}) WHERE id=%s",
            (message, int(event["id"])),
        )
    connection.commit()


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


def _identity(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def _mysql_code(error: OperationalError) -> int:
    return int(error.args[0]) if error.args else 0


__all__ = [
    "HistoricalOrderReviewRemediationOutboxResult",
    "consume_historical_order_review_remediation_events",
]

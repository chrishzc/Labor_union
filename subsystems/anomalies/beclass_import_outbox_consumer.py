"""
File: beclass_import_outbox_consumer.py
Description: 投影 BeClass open／auto-resolved 警示，未知 issue 以三次一秒政策停損。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json

from pymysql.err import OperationalError

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.import_warning_tracking import ImportWarningTrackingStatus
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from domains.case_import.beclass_warning_review import build_beclass_warning_occurrences
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from subsystems.anomalies.alert_workflow import AnomalyApplication
from subsystems.anomalies.beclass_import_anomaly_consumer import BeClassImportReviewItem, consume_beclass_import_review_item
from subsystems.anomalies.import_warning_projection_retry import (
    MAX_WARNING_PROJECTION_ATTEMPTS,
    WARNING_PROJECTION_RETRY_DELAY_SECONDS,
    WARNING_PROJECTION_RETRY_READY_SQL,
    warning_projection_error_code,
)


@dataclass(frozen=True, slots=True)
class BeClassImportOutboxResult:
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


def consume_beclass_import_review_events(connection, *, maximum_events: int = 50) -> BeClassImportOutboxResult:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        outcome = _consume_next(connection)
        if outcome is None:
            break
        if outcome:
            delivered += 1
        else:
            failed += 1
    return BeClassImportOutboxResult(delivered, failed)


def _consume_next(connection):
    event = None
    try:
        event = _claim_next(connection)
        if event is None:
            connection.rollback()
            return None
        warning_projection = _build_warning_projection(connection, event)
        review_item = _review_item(event)
        if warning_projection is not None:
            review, warnings, evidence = warning_projection
            review_item = replace(
                review_item,
                active=any(
                    warning.tracking_status
                    is not ImportWarningTrackingStatus.AUTO_RESOLVED
                    for warning in warnings
                ),
            )
        application = AnomalyApplication(default_anomaly_registry(), MySqlAnomalyRepository(connection), BorrowedUnitOfWork)
        consume_beclass_import_review_item(application, review_item)
        if warning_projection is not None:
            _project_warning_occurrences(
                connection,
                warnings,
                str(review["review_identity"]),
                evidence,
            )
        _mark_delivered(connection, int(event["id"]))
        connection.commit()
        return True
    except OperationalError as error:
        connection.rollback()
        if event is None:
            raise
        _mark_failed(connection, event, error)
        return False
    except Exception as error:
        connection.rollback()
        _mark_failed(connection, event, error)
        return False


def _claim_next(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,review_row_id,intent_type,bounded_snapshot,created_at "
            "FROM beclass_import_review_outbox WHERE published_at IS NULL "
            f"AND attempts<{MAX_WARNING_PROJECTION_ATTEMPTS} "
            f"AND {WARNING_PROJECTION_RETRY_READY_SQL} "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _review_item(event):
    snapshot = _json_object(event["bounded_snapshot"])
    return BeClassImportReviewItem(
        definition_code=str(snapshot["definition_code"]), review_item_id=str(snapshot["review_item_id"]), entity_kind=str(snapshot["entity_kind"]),
        source_sheet=str(snapshot["source_sheet"]), source_row=int(snapshot["source_row"]), error_codes=tuple(sorted(set(snapshot["error_codes"]))),
        source_version=int(snapshot["version"]), masked_identifier=str(snapshot["masked_identifier"]), active=bool(snapshot["active"]),
        source_event_id=f"beclass-review-outbox:{event['id']}", occurred_at=_aware_datetime(event["created_at"]),
    )


def _build_warning_projection(connection, event):
    if str(event["intent_type"]) != "review_opened":
        return None
    review = _load_review(connection, int(event["review_row_id"]))
    warnings = build_beclass_warning_occurrences(
        source_kind=BeClassImportSourceKind(str(review["source_kind"])),
        source_event_identity=str(review["source_event_identity"]),
        masked_identifier=str(review["masked_identifier"]),
        issue_codes=_text_tuple(review["issue_codes"]),
    )
    evidence = _json_object(review["source_payload"])
    return review, warnings, evidence


def _project_warning_occurrences(
    connection, warnings, review_identity: str, evidence
) -> None:
    for warning in warnings:
        _append_warning_occurrence(connection, warning, review_identity, evidence)


def _load_review(connection, review_row_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT review_identity,source_kind,source_event_identity,masked_identifier,"
            "source_payload,issue_codes FROM beclass_import_review_rows "
            "WHERE id=%s FOR UPDATE",
            (review_row_id,),
        )
        review = cursor.fetchone()
    if review is None:
        raise RuntimeError("beclass_import_review_root_missing")
    return review


def _append_warning_occurrence(connection, warning, review_identity: str, evidence) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT IGNORE INTO import_warning_occurrences "
            "(occurrence_identity,owning_lane,source_kind,source_event_identity,source_receipt_identity,logical_code,field_path,masked_subject,issue_codes,evidence_snapshot) "
            "VALUES (%s,%s,'beclass_review',%s,%s,%s,%s,%s,%s,%s)",
            (warning.occurrence_identity, warning.owning_lane, warning.source_event_identity,
             review_identity, warning.logical_code, warning.field_path, warning.masked_subject,
             _json(list(warning.issue_codes)), _json(evidence)),
        )
        cursor.execute("SELECT id FROM import_warning_occurrences WHERE occurrence_identity=%s FOR UPDATE", (warning.occurrence_identity,))
        occurrence = cursor.fetchone()
        if occurrence is None:
            raise RuntimeError("beclass_warning_occurrence_missing")
        occurrence_id = int(occurrence["id"])
        initial_status = warning.tracking_status.value
        if warning.tracking_status is ImportWarningTrackingStatus.AUTO_RESOLVED:
            action = "auto_resolved"
            reason_code = "owner_predicate_already_satisfied"
            key = _identity(
                "beclass-warning-auto-resolved", warning.occurrence_identity
            )
        else:
            action = "opened"
            reason_code = "source_review_opened"
            key = _identity("beclass-warning-open", warning.occurrence_identity)
        cursor.execute(
            "INSERT IGNORE INTO import_warning_tracking_events "
            "(event_identity,occurrence_id,action,before_status,after_status,expected_version,resulting_version,actor_kind,actor_identity,reason_code,command_fingerprint,idempotency_key,correlation_id) "
            "VALUES (%s,%s,%s,NULL,%s,0,1,'system','beclass-review-projector',%s,%s,%s,%s)",
            (
                key,
                occurrence_id,
                action,
                initial_status,
                reason_code,
                _identity("beclass-warning-fingerprint", warning.occurrence_identity),
                key,
                key,
            ),
        )
        cursor.execute("SELECT id FROM import_warning_tracking_events WHERE idempotency_key=%s", (key,))
        event = cursor.fetchone()
        if event is None:
            raise RuntimeError("beclass_warning_open_event_missing")
        cursor.execute(
            "INSERT IGNORE INTO import_warning_current_tasks "
            "(occurrence_id,tracking_status,tracking_version,last_event_id) VALUES (%s,%s,1,%s)",
            (occurrence_id, initial_status, int(event["id"])),
        )


def _mark_delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE beclass_import_review_outbox SET published_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s AND published_at IS NULL", (event_id,))
        if int(cursor.rowcount) != 1:
            raise RuntimeError("beclass_import_outbox_delivery_conflict")


def _mark_failed(connection, event, error):
    if not isinstance(event, dict) or "id" not in event:
        return None
    with connection.cursor() as cursor:
        message = warning_projection_error_code(error, owning_lane="beclass_review")
        cursor.execute(
            "UPDATE beclass_import_review_outbox SET attempts=attempts+1,"
            "last_error=JSON_OBJECT('error_code',%s,'retry_after_epoch',"
            f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {WARNING_PROJECTION_RETRY_DELAY_SECONDS} SECOND)),"
            f"'terminal',attempts+1>={MAX_WARNING_PROJECTION_ATTEMPTS}) WHERE id=%s",
            (message, int(event["id"])),
        )
    connection.commit()


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("BeClass review outbox snapshot must be an object")
    return parsed


def _text_tuple(value) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("BeClass review issue codes must be an array")
    return tuple(sorted({str(item) for item in parsed}))


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def _aware_datetime(value):
    if not isinstance(value, datetime):
        raise ValueError("BeClass review outbox created_at must be datetime")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

"""
File: historical_order_adoption_outbox_consumer.py
Description: 投影歷史訂單去敏警示，未知 issue 以三次一秒政策停損。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from pymysql.err import OperationalError

from domains.anomalies.registry import DesiredAlertState, default_anomaly_registry
from domains.orders.historical_order_warning_review import (
    build_historical_order_warning_occurrences,
)
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest
from subsystems.anomalies.import_warning_projection_retry import (
    MAX_WARNING_PROJECTION_ATTEMPTS,
    WARNING_PROJECTION_RETRY_DELAY_SECONDS,
    WARNING_PROJECTION_RETRY_READY_SQL,
    warning_projection_error_code,
)


@dataclass(frozen=True, slots=True)
class HistoricalOrderAdoptionOutboxResult:
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


def consume_historical_order_adoption_review_events(
    connection, *, maximum_events: int = 50
) -> HistoricalOrderAdoptionOutboxResult:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        outcome = _consume_next(connection)
        if outcome is None:
            break
        delivered += int(outcome)
        failed += int(not outcome)
    return HistoricalOrderAdoptionOutboxResult(delivered, failed)


def _consume_next(connection):
    event = None
    try:
        event = _claim_next(connection)
        if event is None:
            connection.rollback()
            return None
        review = _load_review(connection, _review_identity(event))
        application = AnomalyApplication(
            default_anomaly_registry(), MySqlAnomalyRepository(connection), BorrowedUnitOfWork
        )
        application.project(_project_request(event, review))
        _project_warning_occurrences(connection, review)
        _mark_delivered(connection, int(event["id"]))
        connection.commit()
        return True
    except OperationalError as error:
        connection.rollback()
        if event is None and _mysql_code(error) == 1146:
            return None
        _mark_failed(connection, event, error)
        return False
    except Exception as error:
        connection.rollback()
        _mark_failed(connection, event, error)
        return False


def _claim_next(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,bounded_snapshot FROM historical_order_adoption_outbox "
            "WHERE intent_type='historical_order_review_required' AND published_at IS NULL "
            f"AND attempts<{MAX_WARNING_PROJECTION_ATTEMPTS} "
            f"AND {WARNING_PROJECTION_RETRY_READY_SQL} "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _review_identity(event) -> str:
    value = _json_object(event["bounded_snapshot"]).get("review_identity")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("historical_order_review_identity_missing")
    return value


def _load_review(connection, review_identity: str):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT review_identity,source_event_identity,masked_case_identity,issue_codes,evidence_snapshot FROM "
            "historical_order_adoption_reviews WHERE review_identity=%s FOR UPDATE",
            (review_identity,),
        )
        review = cursor.fetchone()
    if not isinstance(review, dict):
        raise ValueError("historical_order_review_root_missing")
    return review


def _project_request(event, review) -> ProjectAlertRequest:
    review_identity = str(review["review_identity"])
    masked_case_identity = str(review["masked_case_identity"])
    issue_codes = _text_tuple(review["issue_codes"])
    return ProjectAlertRequest(
        desired=DesiredAlertState(
            definition_code="HISTORICAL-ORDER-001",
            source_identity=review_identity,
            source_version=0,
            active=True,
            fingerprint_values={"review_identity": review_identity},
        ),
        source_event_identity=f"historical-order-review-outbox:{event['id']}",
        consumer_identity="historical-order-review-anomaly-projector-v1",
        partition_identity=f"HISTORICAL-ORDER-001:{review_identity}",
        display_snapshot={
            "review_identity": review_identity,
            "masked_case_identity": masked_case_identity,
            "issue_codes": issue_codes,
        },
    )


def _project_warning_occurrences(connection, review) -> None:
    warnings = build_historical_order_warning_occurrences(
        source_event_identity=str(review["source_event_identity"]),
        masked_case_identity=str(review["masked_case_identity"]),
        issue_codes=_text_tuple(review["issue_codes"]),
    )
    evidence = _json_object(review["evidence_snapshot"])
    for warning in warnings:
        append_historical_order_warning_occurrence(
            connection,
            warning,
            str(review["review_identity"]),
            evidence,
        )


def append_historical_order_warning_occurrence(
    connection, warning, review_identity: str, evidence
) -> None:
    """Append one owner-validated historical warning inside the caller's UoW."""
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT IGNORE INTO import_warning_occurrences "
            "(occurrence_identity,owning_lane,source_kind,source_event_identity,source_receipt_identity,logical_code,field_path,masked_subject,issue_codes,evidence_snapshot) "
            "VALUES (%s,%s,'historical_order_review',%s,%s,%s,%s,%s,%s,%s)",
            (
                warning.occurrence_identity,
                warning.owning_lane,
                warning.source_event_identity,
                review_identity,
                warning.logical_code,
                warning.field_path,
                warning.masked_subject,
                _json(list(warning.issue_codes)),
                _json(evidence),
            ),
        )
        cursor.execute(
            "SELECT id FROM import_warning_occurrences WHERE occurrence_identity=%s FOR UPDATE",
            (warning.occurrence_identity,),
        )
        occurrence = cursor.fetchone()
        if occurrence is None:
            raise RuntimeError("historical_order_warning_occurrence_missing")
        occurrence_id = int(occurrence["id"])
        key = _identity("historical-order-warning-open", warning.occurrence_identity)
        cursor.execute(
            "INSERT IGNORE INTO import_warning_tracking_events "
            "(event_identity,occurrence_id,action,before_status,after_status,expected_version,resulting_version,actor_kind,actor_identity,reason_code,command_fingerprint,idempotency_key,correlation_id) "
            "VALUES (%s,%s,'opened',NULL,'open',0,1,'system','historical-order-projector','source_review_opened',%s,%s,%s)",
            (
                key,
                occurrence_id,
                _identity("historical-order-warning-fingerprint", warning.occurrence_identity),
                key,
                key,
            ),
        )
        cursor.execute(
            "SELECT id FROM import_warning_tracking_events WHERE idempotency_key=%s",
            (key,),
        )
        event = cursor.fetchone()
        if event is None:
            raise RuntimeError("historical_order_warning_open_event_missing")
        cursor.execute(
            "INSERT IGNORE INTO import_warning_current_tasks "
            "(occurrence_id,tracking_status,tracking_version,last_event_id) VALUES (%s,'open',1,%s)",
            (occurrence_id, int(event["id"])),
        )


def _mark_delivered(connection, event_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE historical_order_adoption_outbox SET published_at=CURRENT_TIMESTAMP,"
            "last_error=NULL WHERE id=%s AND published_at IS NULL",
            (event_id,),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("historical_order_adoption_outbox_delivery_conflict")


def _mark_failed(connection, event, error: Exception) -> None:
    if not isinstance(event, dict) or "id" not in event:
        return
    with connection.cursor() as cursor:
        message = warning_projection_error_code(error, owning_lane="historical_order")
        cursor.execute(
            "UPDATE historical_order_adoption_outbox SET attempts=attempts+1,"
            "last_error=JSON_OBJECT('error_code',%s,'retry_after_epoch',"
            f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {WARNING_PROJECTION_RETRY_DELAY_SECONDS} SECOND)),"
            f"'terminal',attempts+1>={MAX_WARNING_PROJECTION_ATTEMPTS}) WHERE id=%s",
            (message, int(event["id"])),
        )
    connection.commit()


def _json_object(value) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("historical order outbox snapshot must be an object")
    return parsed


def _text_tuple(value) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("historical order review issue codes must be an array")
    return tuple(sorted({str(item) for item in parsed}))


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def _mysql_code(error: OperationalError) -> int:
    return int(error.args[0]) if error.args else 0


__all__ = [
    "HistoricalOrderAdoptionOutboxResult",
    "append_historical_order_warning_occurrence",
    "consume_historical_order_adoption_review_events",
]

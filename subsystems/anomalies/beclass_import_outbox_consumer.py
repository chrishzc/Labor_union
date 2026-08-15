"""
File: beclass_import_outbox_consumer.py
Description: 將 BeClass review outbox事件投影至 canonical anomaly workflow。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from pymysql.err import OperationalError

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from subsystems.anomalies.alert_workflow import AnomalyApplication
from subsystems.anomalies.beclass_import_anomaly_consumer import BeClassImportReviewItem, consume_beclass_import_review_item


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
        application = AnomalyApplication(default_anomaly_registry(), MySqlAnomalyRepository(connection), BorrowedUnitOfWork)
        consume_beclass_import_review_item(application, _review_item(event))
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
        cursor.execute("SELECT id,bounded_snapshot,created_at FROM beclass_import_review_outbox WHERE published_at IS NULL AND attempts<10 ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED")
        return cursor.fetchone()


def _review_item(event):
    snapshot = _json_object(event["bounded_snapshot"])
    return BeClassImportReviewItem(
        definition_code=str(snapshot["definition_code"]), review_item_id=str(snapshot["review_item_id"]), entity_kind=str(snapshot["entity_kind"]),
        source_sheet=str(snapshot["source_sheet"]), source_row=int(snapshot["source_row"]), error_codes=tuple(sorted(set(snapshot["error_codes"]))),
        source_version=int(snapshot["version"]), masked_identifier=str(snapshot["masked_identifier"]), active=bool(snapshot["active"]),
        source_event_id=f"beclass-review-outbox:{event['id']}", occurred_at=_aware_datetime(event["created_at"]),
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
        cursor.execute("UPDATE beclass_import_review_outbox SET attempts=attempts+1,last_error=%s WHERE id=%s", ((str(error) or "BeClass anomaly projection failed")[:500], int(event["id"])))
    connection.commit()


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("BeClass review outbox snapshot must be an object")
    return parsed


def _aware_datetime(value):
    if not isinstance(value, datetime):
        raise ValueError("BeClass review outbox created_at must be datetime")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

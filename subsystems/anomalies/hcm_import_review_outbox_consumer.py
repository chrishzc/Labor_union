"""
File: hcm_import_review_outbox_consumer.py
Description: 將 HCM review outbox 可重試地投影為 canonical IMPORT-004 anomaly。
"""

from __future__ import annotations

from dataclasses import dataclass
import json

from pymysql.err import OperationalError

from domains.anomalies.registry import DesiredAlertState, default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest


@dataclass(frozen=True, slots=True)
class HcmImportReviewOutboxResult:
    delivered_count: int
    failed_count: int


class BorrowedUnitOfWork:
    def __enter__(self): return self
    def __exit__(self, exception_type, exception, traceback): return False
    def commit(self): return None
    def rollback(self): return None


def consume_hcm_import_review_events(connection, *, maximum_events: int = 50):
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        outcome = _consume_next(connection)
        if outcome is None:
            break
        delivered += int(outcome)
        failed += int(not outcome)
    return HcmImportReviewOutboxResult(delivered, failed)


def _consume_next(connection):
    event = None
    try:
        event = _claim_next(connection)
        if event is None:
            connection.rollback()
            return None
        snapshot = _json_object(event["bounded_snapshot"])
        application = AnomalyApplication(
            default_anomaly_registry(),
            MySqlAnomalyRepository(connection),
            BorrowedUnitOfWork,
        )
        application.project(_project_request(event, snapshot))
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


def _project_request(event, snapshot):
    review_identity = str(snapshot["review_identity"])
    masked_case_identity = str(snapshot["masked_case_identity"])
    return ProjectAlertRequest(
        desired=DesiredAlertState(
            definition_code="IMPORT-004",
            source_identity=review_identity,
            source_version=int(snapshot["source_version"]),
            active=bool(snapshot["active"]),
            fingerprint_values={"case_no": masked_case_identity},
        ),
        source_event_identity=f"hcm-review-outbox:{event['id']}",
        consumer_identity="hcm-import-review-anomaly-projector-v1",
        partition_identity=f"IMPORT-004:{review_identity}",
        display_snapshot={
            "review_identity": review_identity,
            "source_row": int(snapshot["source_row"]),
            "masked_case_identity": masked_case_identity,
            "issue_codes": tuple(sorted(set(snapshot["issue_codes"]))),
        },
    )


def _claim_next(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,bounded_snapshot FROM case_import_hcm_review_outbox "
            "WHERE published_at IS NULL AND attempts<10 ORDER BY id LIMIT 1 "
            "FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _mark_delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE case_import_hcm_review_outbox SET published_at=CURRENT_TIMESTAMP,"
            "last_error=NULL WHERE id=%s AND published_at IS NULL",
            (event_id,),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("case_import_hcm_review_outbox_delivery_conflict")


def _mark_failed(connection, event, error):
    if not isinstance(event, dict) or "id" not in event:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE case_import_hcm_review_outbox SET attempts=attempts+1,last_error=%s WHERE id=%s",
            ((str(error) or "HCM anomaly projection failed")[:500], int(event["id"])),
        )
    connection.commit()


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("HCM review outbox snapshot must be an object")
    return parsed


def _mysql_code(error):
    return int(error.args[0]) if error.args else 0


__all__ = ["HcmImportReviewOutboxResult", "consume_hcm_import_review_events"]

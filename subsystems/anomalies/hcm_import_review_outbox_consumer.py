"""
File: hcm_import_review_outbox_consumer.py
Description: 將通過匯入門檻的 HCM review 投影為警示，未知 issue 重試後停損。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from pymysql.err import OperationalError

from domains.anomalies.registry import DesiredAlertState, default_anomaly_registry
from domains.case_import.hcm_import_review import build_hcm_warning_occurrences_from_review
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest
from subsystems.anomalies.import_warning_projection_retry import (
    MAX_WARNING_PROJECTION_ATTEMPTS,
    WARNING_PROJECTION_RETRY_DELAY_SECONDS,
    WARNING_PROJECTION_RETRY_READY_SQL,
    warning_projection_error_code,
)


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
        warning_count = _project_warning_occurrences(connection, snapshot)
        if warning_count:
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
            f"WHERE published_at IS NULL AND attempts<{MAX_WARNING_PROJECTION_ATTEMPTS} "
            f"AND {WARNING_PROJECTION_RETRY_READY_SQL} ORDER BY id LIMIT 1 "
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


def _project_warning_occurrences(connection, snapshot):
    review = _load_review(connection, str(snapshot["review_identity"]))
    if review is None:
        raise RuntimeError("hcm_import_review_root_missing")
    issue_codes = _json_array(review["issue_codes"])
    evidence = _json_object(review["evidence_snapshot"])
    warnings = build_hcm_warning_occurrences_from_review(
        source_event_identity=str(review["source_event_identity"]),
        masked_case_identity=str(review["masked_case_identity"]),
        issue_codes=tuple(str(item) for item in issue_codes),
    )
    for warning in warnings:
        _append_warning_occurrence(connection, warning, str(snapshot["review_identity"]), evidence)
    return len(warnings)


def _load_review(connection, review_identity):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_event_identity,masked_case_identity,issue_codes,evidence_snapshot "
            "FROM case_import_hcm_review_rows WHERE review_identity=%s FOR UPDATE",
            (review_identity,),
        )
        return cursor.fetchone()


def _append_warning_occurrence(connection, warning, review_identity, evidence):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT IGNORE INTO import_warning_occurrences "
            "(occurrence_identity,owning_lane,source_kind,source_event_identity,source_receipt_identity,logical_code,field_path,masked_subject,issue_codes,evidence_snapshot) "
            "VALUES (%s,%s,'hcm_review',%s,%s,%s,%s,%s,%s,%s)",
            (warning.occurrence_identity, warning.owning_lane, warning.source_event_identity,
             review_identity, warning.logical_code, warning.field_path, warning.masked_subject,
             _json(list(warning.issue_codes)), _json(evidence)),
        )
        cursor.execute(
            "SELECT id FROM import_warning_occurrences WHERE occurrence_identity=%s FOR UPDATE",
            (warning.occurrence_identity,),
        )
        occurrence = cursor.fetchone()
        if occurrence is None:
            raise RuntimeError("hcm_warning_occurrence_missing")
        occurrence_id = int(occurrence["id"])
        key = _identity("hcm-warning-open", warning.occurrence_identity)
        cursor.execute(
            "INSERT IGNORE INTO import_warning_tracking_events "
            "(event_identity,occurrence_id,action,before_status,after_status,expected_version,resulting_version,actor_kind,actor_identity,reason_code,command_fingerprint,idempotency_key,correlation_id) "
            "VALUES (%s,%s,'opened',NULL,'open',0,1,'system','hcm-review-projector','source_review_opened',%s,%s,%s)",
            (key, occurrence_id, _identity("hcm-warning-fingerprint", warning.occurrence_identity), key, key),
        )
        cursor.execute(
            "SELECT id FROM import_warning_tracking_events WHERE idempotency_key=%s",
            (key,),
        )
        event = cursor.fetchone()
        if event is None:
            raise RuntimeError("hcm_warning_open_event_missing")
        cursor.execute(
            "INSERT IGNORE INTO import_warning_current_tasks "
            "(occurrence_id,tracking_status,tracking_version,last_event_id) VALUES (%s,'open',1,%s)",
            (occurrence_id, int(event["id"])),
        )


def _mark_failed(connection, event, error):
    if not isinstance(event, dict) or "id" not in event:
        return
    with connection.cursor() as cursor:
        message = warning_projection_error_code(error, owning_lane="hcm")
        cursor.execute(
            "UPDATE case_import_hcm_review_outbox SET attempts=attempts+1,"
            "last_error=JSON_OBJECT('error_code',%s,'retry_after_epoch',"
            f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {WARNING_PROJECTION_RETRY_DELAY_SECONDS} SECOND)),"
            f"'terminal',attempts+1>={MAX_WARNING_PROJECTION_ATTEMPTS}) "
            "WHERE id=%s",
            (message, int(event["id"])),
        )
    connection.commit()


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("HCM review outbox snapshot must be an object")
    return parsed


def _json_array(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("HCM review issue codes must be an array")
    return parsed


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(namespace, value):
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def _mysql_code(error):
    return int(error.args[0]) if error.args else 0


__all__ = ["HcmImportReviewOutboxResult", "consume_hcm_import_review_events"]

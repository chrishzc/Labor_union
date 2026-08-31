"""Consume Finance Import projection intents after the owner transaction commits.

Finance Import owns the source outbox and its retry state.  This consumer only
handles the one existing anomaly contract, ``IMPORT-006``; row classification
and source-format review remain Finance Import owner work items.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Protocol

MAX_FINANCE_IMPORT_PROJECTION_ATTEMPTS = 3
FINANCE_IMPORT_PROJECTION_RETRY_DELAY_SECONDS = 1
_RETRY_READY_SQL = (
    "(last_error IS NULL OR JSON_VALID(last_error)=0 OR "
    "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(last_error,'$.retry_after_epoch')) "
    "AS DECIMAL(20,6)),0)<=UNIX_TIMESTAMP(UTC_TIMESTAMP(6)))"
)

_OUTBOX_SELECT_SQL = (
    "SELECT id,intent_type,payload_snapshot,created_at FROM finance_import_outbox "
    "WHERE intent_type IN ('initial_classification_recorded','dispatch_completed',"
    "'manual_correction_completed','refund_return_review_recorded',"
    "'historical_reprocess_completed') AND status IN ('pending','failed') "
    f"AND attempt_count<{MAX_FINANCE_IMPORT_PROJECTION_ATTEMPTS} "
    "AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) "
    "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
)


class FinanceImportRuntime(Protocol):
    """Dependencies composed by the Finance Import application boundary."""

    def failure_unit_of_work(self, connection: Any) -> Any: ...

    def project_finance_import_review_alert(
        self, cursor: Any, batch_id: int, **kwargs: Any
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class FinanceImportAnomalyConsumerResult:
    delivered_count: int
    failed_count: int


def consume_finance_import_anomaly_events(connection, *, maximum_events: int = 50, runtime: FinanceImportRuntime | None = None) -> FinanceImportAnomalyConsumerResult:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    runtime = _require_runtime(runtime)
    delivered = failed = 0
    for _ in range(maximum_events):
        outcome = _consume_next(connection, runtime)
        if outcome is None:
            break
        if outcome:
            delivered += 1
        else:
            failed += 1
    return FinanceImportAnomalyConsumerResult(delivered, failed)


def _consume_next(connection, runtime: FinanceImportRuntime):
    try:
        event = _claim_next_event(connection)
        if event is None:
            connection.rollback()
            return None
        _mark_delivered(connection, event)
        connection.commit()
        return True
    except Exception as error:
        connection.rollback()
        _record_failure(connection, locals().get("event"), error, runtime)
        return False


def _claim_next_event(connection):
    source_review = _claim_next_source_review(connection)
    if source_review is not None:
        return source_review
    with connection.cursor() as cursor:
        cursor.execute(_OUTBOX_SELECT_SQL)
        event = cursor.fetchone()
    if event is not None:
        event["outbox_kind"] = "finance_event"
    return event


def _claim_next_source_review(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,review_id,'source_review_opened' AS intent_type,"
            "'source_review' AS outbox_kind,created_at "
            "FROM finance_import_source_review_outbox "
            "WHERE published_at IS NULL "
            f"AND attempts<{MAX_FINANCE_IMPORT_PROJECTION_ATTEMPTS} "
            f"AND {_RETRY_READY_SQL} "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _project_historical_reprocess_integrity(connection, event, runtime: FinanceImportRuntime) -> None:
    payload = _json_object(event["payload_snapshot"])
    batch_id = _prefixed_positive_integer(
        payload.get("batch_identity"),
        "finance-import-batch:",
    )
    event_id = _positive_integer(event["id"])
    with connection.cursor() as cursor:
        runtime.project_finance_import_review_alert(
            cursor,
            batch_id,
            source_version=event_id,
            source_event_identity=f"finance-import-historical-reprocess:{event_id}",
        )


def _mark_delivered(connection, event):
    with connection.cursor() as cursor:
        if event.get("outbox_kind") == "source_review":
            cursor.execute(
                "UPDATE finance_import_source_review_outbox "
                "SET published_at=CURRENT_TIMESTAMP,last_error=NULL "
                "WHERE id=%s AND published_at IS NULL",
                (int(event["id"]),),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("finance_source_review_delivery_conflict")
            return
        cursor.execute("UPDATE finance_import_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s AND status IN ('pending','failed')", (int(event["id"]),))
        if cursor.rowcount != 1:
            raise RuntimeError("finance_import_outbox_delivery_conflict")


def _mark_failed(connection, event, error):
    if not isinstance(event, dict) or "id" not in event:
        return None
    with connection.cursor() as cursor:
        message = _projection_error_code(error)
        if event.get("outbox_kind") == "source_review":
            cursor.execute(
                "UPDATE finance_import_source_review_outbox SET attempts=attempts+1,"
                "last_error=JSON_OBJECT('error_code',%s,'retry_after_epoch',"
                f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {FINANCE_IMPORT_PROJECTION_RETRY_DELAY_SECONDS} SECOND)),"
                f"'terminal',attempts+1>={MAX_FINANCE_IMPORT_PROJECTION_ATTEMPTS}) "
                "WHERE id=%s",
                (message, int(event["id"])),
            )
            return
        cursor.execute(
            "UPDATE finance_import_outbox SET status='failed',"
            "attempt_count=attempt_count+1,"
            f"next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL {FINANCE_IMPORT_PROJECTION_RETRY_DELAY_SECONDS} SECOND),"
            "last_error=JSON_OBJECT('error_code',%s,'terminal',"
            f"attempt_count+1>={MAX_FINANCE_IMPORT_PROJECTION_ATTEMPTS}) WHERE id=%s",
            (message, int(event["id"])),
        )


def _record_failure(connection, event, error, runtime: FinanceImportRuntime):
    if not isinstance(event, dict) or "id" not in event:
        return None
    with runtime.failure_unit_of_work(connection) as unit_of_work:
        _mark_failed(connection, event, error)
        unit_of_work.commit()


def _json_object(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("outbox payload must be object")
    return payload


def _prefixed_positive_integer(value, prefix):
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("Finance Import outbox identity is invalid")
    raw_value = value.removeprefix(prefix)
    if not raw_value.isdigit() or int(raw_value) <= 0:
        raise ValueError("Finance Import outbox identity is invalid")
    return int(raw_value)


def _positive_integer(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Finance Import outbox positive integer is invalid")
    return value


def _require_runtime(runtime: FinanceImportRuntime | None) -> FinanceImportRuntime:
    if runtime is None:
        raise RuntimeError("finance_import_runtime_not_composed")
    if not callable(getattr(runtime, "failure_unit_of_work", None)) or not callable(
        getattr(runtime, "project_finance_import_review_alert", None)
    ):
        raise RuntimeError("finance_import_runtime_not_composed")
    return runtime


def _projection_error_code(error: Exception) -> str:
    """Return a bounded, non-sensitive retry diagnostic for this owner queue."""

    message = str(error).strip()
    digest = hashlib.sha256(
        f"{type(error).__name__}:{message}".encode("utf-8")
    ).hexdigest()[:16]
    return f"finance_import_projection_failed:{digest}"

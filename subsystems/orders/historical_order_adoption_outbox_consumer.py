"""
File: historical_order_adoption_outbox_consumer.py
Description: 消費 Orders 歷史訂單 review outbox，保留 canonical receipt 與 bounded retry。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Mapping

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
class HistoricalOrderAdoptionOutboxResult:
    delivered_count: int
    failed_count: int


def consume_historical_order_adoption_review_events(
    connection,
    *,
    maximum_events: int = 50,
    runtime: HistoricalOrderOutboxRuntime | None = None,
) -> HistoricalOrderAdoptionOutboxResult:
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
    return HistoricalOrderAdoptionOutboxResult(delivered, failed)


def _consume_next(connection, runtime: HistoricalOrderOutboxRuntime):
    event = None
    try:
        event = _claim_next(connection)
        if event is None:
            connection.rollback()
            return None
        receipt = _load_receipt(connection, int(event["receipt_id"]))
        review_identity = _review_identity(event)
        review = _load_review(connection, review_identity)
        _validate_canonical_event(event, receipt, review, review_identity)
        _mark_delivered(connection, int(event["id"]))
        connection.commit()
        return True
    except OperationalError as error:
        connection.rollback()
        if event is None and _mysql_code(error) == 1146:
            return None
        _record_failure(connection, event, error, runtime)
        return False
    except Exception as error:
        connection.rollback()
        _record_failure(connection, event, error, runtime)
        return False


def _claim_next(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,receipt_id,intent_type,bounded_snapshot FROM historical_order_adoption_outbox "
            "WHERE intent_type='historical_order_review_required' AND published_at IS NULL "
            f"AND attempts<{HISTORICAL_ORDER_OUTBOX_MAX_ATTEMPTS} "
            f"AND {HISTORICAL_ORDER_OUTBOX_RETRY_READY_SQL} "
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


def _load_receipt(connection, receipt_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,source_event_identity,source_fingerprint,preview_fingerprint,"
            "case_no,outcome,review_identity,result_snapshot "
            "FROM historical_order_adoption_receipts WHERE id=%s FOR UPDATE",
            (receipt_id,),
        )
        receipt = cursor.fetchone()
    if not isinstance(receipt, Mapping):
        raise ValueError("historical_order_adoption_receipt_missing")
    return receipt


def _validate_canonical_event(event, receipt, review, review_identity: str) -> None:
    """Require the immutable Orders receipt/review pair before acknowledging."""

    if int(receipt["id"]) != int(event["receipt_id"]):
        raise ValueError("historical_order_adoption_receipt_binding_mismatch")
    if event.get("intent_type") != "historical_order_review_required":
        raise ValueError("historical_order_adoption_intent_type_invalid")
    if receipt.get("outcome") not in {
        "adopted",
        "review_required",
        "current_conflict",
    }:
        raise ValueError("historical_order_adoption_review_outcome_invalid")
    if receipt.get("review_identity") != review_identity:
        raise ValueError("historical_order_adoption_review_binding_mismatch")
    if review.get("review_identity") != review_identity:
        raise ValueError("historical_order_review_binding_mismatch")
    if not isinstance(review.get("source_event_identity"), str) or not review["source_event_identity"].strip():
        raise ValueError("historical_order_review_source_missing")
    if not isinstance(review.get("masked_case_identity"), str) or not review["masked_case_identity"].strip():
        raise ValueError("historical_order_review_masked_identity_missing")
    _text_tuple(review.get("issue_codes"))
    _json_object(review.get("evidence_snapshot"))
    _json_object(receipt.get("result_snapshot"))
    snapshot = _json_object(event.get("bounded_snapshot"))
    if snapshot.get("review_identity") != review_identity:
        raise ValueError("historical_order_adoption_event_review_binding_mismatch")


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
        message = historical_order_outbox_error_code(error)
        cursor.execute(
            "UPDATE historical_order_adoption_outbox SET attempts=attempts+1,"
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
        raise ValueError("historical order outbox snapshot must be an object")
    return parsed


def _text_tuple(value) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("historical order review issue codes must be an array")
    return tuple(sorted({str(item) for item in parsed}))


def _mysql_code(error: OperationalError) -> int:
    return int(error.args[0]) if error.args else 0


__all__ = [
    "HistoricalOrderAdoptionOutboxResult",
    "consume_historical_order_adoption_review_events",
]

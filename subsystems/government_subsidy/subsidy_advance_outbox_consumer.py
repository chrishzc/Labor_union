"""Deliver Government Subsidy allocation facts to Client Finance recovery."""

from __future__ import annotations

import json
from typing import Any, Callable

from shared_kernel.money import MoneyNTD
from subsystems.client_finance.subsidy_advance_recovery import (
    GovernmentReceiptAllocationEvent,
    SubsidyAdvanceRecoveryRepository,
    SubsidyAdvanceRecoveryWorkflow,
)


def consume_government_subsidy_advance_events(
    connection,
    repository_factory: Callable[[Any], SubsidyAdvanceRecoveryRepository],
    maximum_events: int = 50,
) -> tuple[int, int]:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        event = _claim_next_event(connection)
        if event is None:
            connection.rollback()
            break
        try:
            _consume_event(connection, event, repository_factory)
            connection.commit()
            delivered += 1
        except Exception:
            connection.rollback()
            _mark_failed(connection, event["id"])
            connection.commit()
            failed += 1
    return delivered, failed


def _consume_event(
    connection,
    event,
    repository_factory: Callable[[Any], SubsidyAdvanceRecoveryRepository],
) -> None:
    payload = _payload(event["payload_snapshot"])
    workflow = SubsidyAdvanceRecoveryWorkflow(repository_factory(connection))
    for allocation in payload["allocations"]:
        workflow.consume(_allocation_event(event, payload, allocation))
    _mark_delivered(connection, event["id"])


def _allocation_event(event, payload, allocation):
    transaction_id = _positive(payload["transaction_id"])
    claim_item_id = _positive(allocation["claim_item_id"])
    return GovernmentReceiptAllocationEvent(
        _positive(event["id"]),
        f"government-allocation:{transaction_id}:{claim_item_id}",
        transaction_id,
        str(allocation["case_no"]),
        claim_item_id,
        MoneyNTD(_positive(allocation["amount_ntd"])),
    )


def _claim_next_event(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id,payload_snapshot FROM government_subsidy_outbox WHERE intent_type='government_subsidy_receipt_allocated' AND status IN ('pending','failed') AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED")
        return cursor.fetchone()


def _mark_delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE government_subsidy_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s AND status IN ('pending','failed')", (event_id,))
        if cursor.rowcount != 1:
            raise RuntimeError("government_subsidy_outbox_delivery_conflict")


def _mark_failed(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE government_subsidy_outbox SET status='failed',attempt_count=attempt_count+1,next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND),last_error='subsidy advance recovery failed' WHERE id=%s", (event_id,))


def _payload(value):
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, dict) or not isinstance(result.get("allocations"), list):
        raise ValueError("government subsidy allocation payload is invalid")
    return result


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("government subsidy allocation identity is invalid")
    return value

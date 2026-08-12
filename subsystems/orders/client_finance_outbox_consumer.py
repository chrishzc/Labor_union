"""Deliver Client Finance deposit facts into the Orders control aggregate."""

from __future__ import annotations

import json
from collections.abc import Mapping

from subsystems.orders.order_lifecycle_command_envelope import (
    lock_order_lifecycle_command_envelope,
)
from subsystems.orders.order_lifecycle_control_commands import (
    ActualStartReconfirmationRequiredCommand,
    apply_order_lifecycle_control_command,
)


def consume_client_finance_orders_events(connection, maximum_events: int = 50):
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        event = _claim_next_event(connection)
        if event is None:
            connection.rollback()
            break
        try:
            _consume_event(connection, event)
            connection.commit()
            delivered += 1
        except Exception as error:
            connection.rollback()
            _mark_failed(connection, int(event["id"]), error)
            failed += 1
    return delivered, failed


def requeue_incomplete_deposit_projections(connection, maximum_events: int = 50) -> int:
    """Recover legacy worker deliveries that never projected the order state."""

    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum events must be between 1 and 100")
    requeued = 0
    for _ in range(maximum_events):
        event_id = _claim_incomplete_delivery(connection)
        if event_id is None:
            connection.rollback()
            return requeued
        _requeue_delivery(connection, event_id)
        connection.commit()
        requeued += 1
    return requeued


def _claim_next_event(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,case_no,intent_type,intent_key,payload_snapshot "
            "FROM client_finance_outbox "
            "WHERE intent_type IN ('orders_deposit_reconciled','orders_deposit_reversed') "
            "AND status IN ('pending','failed') "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _claim_incomplete_delivery(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT outbox.id FROM client_finance_outbox outbox "
            "JOIN orders order_row ON order_row.case_no=outbox.case_no "
            "JOIN client_deposit_settlement_projection settlement "
            "ON settlement.case_no=outbox.case_no "
            "WHERE outbox.intent_type='orders_deposit_reconciled' "
            "AND outbox.status='delivered' AND order_row.status='洽談中' "
            "AND settlement.settlement_state='settled' "
            "ORDER BY outbox.id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        row = cursor.fetchone()
    return None if row is None else int(row["id"])


def _requeue_delivery(connection, event_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox SET status='pending',delivered_at=NULL,"
            "next_attempt_at=NULL,last_error='requeued_incomplete_deposit_projection' "
            "WHERE id=%s AND status='delivered'",
            (event_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("client_finance_outbox_requeue_conflict")


def _consume_event(connection, event) -> None:
    payload = _payload(event["payload_snapshot"])
    if event["intent_type"] == "orders_deposit_reconciled":
        _project_deposit_established(connection, event, payload)
        _activate_reconfirmation_if_current(connection, event, payload)
    _mark_delivered(connection, int(event["id"]))


def _project_deposit_established(connection, event, payload) -> None:
    """A settled deposit establishes an order even before client signing."""

    settlement_identity = _settlement_identity(payload)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE orders SET status='訂單成立',lifecycle_version=lifecycle_version+1 "
            "WHERE case_no=%s AND status='洽談中'",
            (event["case_no"],),
        )
        if cursor.rowcount != 1:
            return
        cursor.execute(
            "INSERT INTO order_lifecycle_state_events "
            "(case_no,trigger_event,before_status,after_status,actor,business_date,"
            "expected_version,idempotency_key,facts_snapshot) "
            "SELECT case_no,'deposit_reconciled','洽談中','訂單成立',"
            "'client-finance-outbox',CURRENT_DATE,lifecycle_version-1,%s,"
            "JSON_OBJECT('deposit_settlement_identity',%s) "
            "FROM orders WHERE case_no=%s",
            (event["intent_key"], settlement_identity, event["case_no"]),
        )


def _activate_reconfirmation_if_current(connection, event, payload) -> None:
    settlement_identity = _settlement_identity(payload)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT lifecycle_version,actual_start_date FROM orders "
            "WHERE case_no=%s FOR UPDATE",
            (event["case_no"],),
        )
        order = cursor.fetchone()
        if not isinstance(order, Mapping):
            raise RuntimeError("orders deposit target is missing")
        if order["actual_start_date"] is None:
            return
        control_idempotency_key = f"{event['intent_key']}:actual-start"
        envelope = lock_order_lifecycle_command_envelope(
            cursor,
            str(event["case_no"]),
            int(order["lifecycle_version"]),
            control_idempotency_key,
        )
        if not _current_settlement_matches(cursor, event["case_no"], settlement_identity):
            return
        command = ActualStartReconfirmationRequiredCommand(
            "client-finance-outbox",
            "deposit settlement identity changed after client receipt reconciliation",
            envelope.lifecycle_version,
            control_idempotency_key,
            envelope.actual_start_date,
            settlement_identity,
        )
        apply_order_lifecycle_control_command(cursor, envelope, command)


def _current_settlement_matches(cursor, case_no, settlement_identity) -> bool:
    cursor.execute(
        "SELECT settlement_state,settlement_identity "
        "FROM client_deposit_settlement_projection WHERE case_no=%s FOR UPDATE",
        (case_no,),
    )
    row = cursor.fetchone()
    return (
        isinstance(row, Mapping)
        and row.get("settlement_state") == "settled"
        and row.get("settlement_identity") == settlement_identity
    )


def _mark_delivered(connection, event_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox "
            "SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL "
            "WHERE id=%s AND status IN ('pending','failed')",
            (event_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("client_finance_outbox_delivery_conflict")


def _mark_failed(connection, event_id: int, error: Exception) -> None:
    error_message = _delivery_error_message(error)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox SET status='failed',"
            "attempt_count=attempt_count+1,"
            "next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND),"
            "last_error=%s WHERE id=%s",
            (error_message, event_id),
        )
    connection.commit()


def _delivery_error_message(error: Exception) -> str:
    message = str(error).strip() or "orders deposit control delivery failed"
    return f"{type(error).__name__}: {message}"[:1000]


def _payload(value) -> Mapping[str, object]:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, Mapping):
        raise ValueError("client finance outbox payload is invalid")
    return payload


def _settlement_identity(payload: Mapping[str, object]) -> str:
    identity = payload.get("settlement_identity")
    if not isinstance(identity, str) or len(identity) != 64:
        raise ValueError("client finance settlement identity is invalid")
    return identity

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
        except Exception:
            connection.rollback()
            _mark_failed(connection, int(event["id"]))
            failed += 1
    return delivered, failed


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


def _consume_event(connection, event) -> None:
    payload = _payload(event["payload_snapshot"])
    if event["intent_type"] == "orders_deposit_reconciled":
        _activate_reconfirmation_if_current(connection, event, payload)
    _mark_delivered(connection, int(event["id"]))


def _activate_reconfirmation_if_current(connection, event, payload) -> None:
    settlement_identity = _settlement_identity(payload)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT lifecycle_version FROM orders WHERE case_no=%s FOR UPDATE",
            (event["case_no"],),
        )
        order = cursor.fetchone()
        if not isinstance(order, Mapping):
            raise RuntimeError("orders deposit target is missing")
        envelope = lock_order_lifecycle_command_envelope(
            cursor,
            str(event["case_no"]),
            int(order["lifecycle_version"]),
            str(event["intent_key"]),
        )
        if envelope.actual_start_date is None:
            return
        if not _current_settlement_matches(cursor, event["case_no"], settlement_identity):
            return
        command = ActualStartReconfirmationRequiredCommand(
            "client-finance-outbox",
            "deposit settlement identity changed after client receipt reconciliation",
            envelope.lifecycle_version,
            str(event["intent_key"]),
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


def _mark_failed(connection, event_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox SET status='failed',"
            "attempt_count=attempt_count+1,"
            "next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND),"
            "last_error='orders deposit control delivery failed' "
            "WHERE id=%s",
            (event_id,),
        )
    connection.commit()


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

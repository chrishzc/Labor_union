"""
File: order_lifecycle_impact_writer.py
Description: 寫入 Orders 條款造成的 typed lifecycle 事件、資料鎖與 outbox。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.order_lifecycle_command_envelope import lock_order_lifecycle_command_envelope
from subsystems.orders.order_lifecycle_control_commands import (
    OrderLifecycleControlConcurrencyError,
    ScheduledStartReconfirmationCarryCommand,
    apply_order_lifecycle_control_command,
)
from subsystems.orders.terms_workflow import (
    LifecycleImpactPersistenceCommand,
)


def persist_order_lifecycle_impact(cursor, command, *, historical_payroll_sync=None) -> int:
    payload = _lifecycle_payload(command)
    if historical_payroll_sync is not None:
        payload["historical_payroll_sync"] = historical_payroll_sync
    snapshot = _canonical_json(payload)
    lifecycle_event_id = _append_lifecycle_event(cursor, command, snapshot)
    if _forms_service_data_lock(command):
        _insert_service_data_lock(cursor, command, lifecycle_event_id)
    _append_orders_outbox(cursor, command, lifecycle_event_id, snapshot)
    return lifecycle_event_id


def persist_order_lifecycle_projection(cursor, command) -> None:
    """Apply the typed lifecycle status projection through the Orders boundary."""
    lifecycle = command.candidate
    cursor.execute(
        _ORDER_PROJECTION_UPDATE_SQL,
        (
            lifecycle.after_status.value,
            lifecycle.actual_end_date,
            getattr(command, "actual_start_date", None),
            getattr(command, "staff_payment_due_date", None),
            command.resulting_order_version,
            lifecycle.case_no,
            command.expected_order_version,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("order_version_conflict")


def persist_order_scheduled_date_projection(
    cursor: Any, *, case_no: str, previous_actual_start_date: date | None,
    actual_start_date: date, actual_end_date: date,
    expected_order_version: int, adjustment_receipt_id: int, actor: str,
) -> None:
    """Synchronize formal service dates while preserving lifecycle events and billing facts."""
    if previous_actual_start_date != actual_start_date:
        _carry_formal_adjustment_reconfirmation(
            cursor, case_no=case_no, previous_actual_start_date=previous_actual_start_date,
            actual_start_date=actual_start_date, expected_order_version=expected_order_version,
            adjustment_receipt_id=adjustment_receipt_id, actor=actor,
        )
    cursor.execute(
        "UPDATE orders SET actual_start_date=%s,actual_end_date=%s,lifecycle_version=lifecycle_version+1 "
        "WHERE case_no=%s AND lifecycle_version=%s",
        (actual_start_date, actual_end_date, case_no, expected_order_version),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("order_version_conflict")


def _carry_formal_adjustment_reconfirmation(
    cursor: Any, *, case_no: str, previous_actual_start_date: date | None,
    actual_start_date: date, expected_order_version: int, adjustment_receipt_id: int,
    actor: str,
) -> None:
    cursor.execute(_SELECT_ADJUSTMENT_RECONFIRMATION_SQL, (case_no,))
    control = cursor.fetchone()
    if control is None:
        return
    confirmed_start = control["confirmed_start_date"]
    if confirmed_start == actual_start_date:
        raise ValueError("service_date_adjustment_stale_source")
    if confirmed_start != previous_actual_start_date or not control["source_matches_current_settlement"]:
        return
    key = f"service-date-adjustment-reconfirmation:{adjustment_receipt_id}"
    envelope = lock_order_lifecycle_command_envelope(cursor, case_no, expected_order_version, key)
    command = ScheduledStartReconfirmationCarryCommand(
        actor=actor,
        reason="沿用正式服務日期調整前的開工重新確認",
        expected_version=expected_order_version,
        idempotency_key=key,
        prior_projected_start_date=confirmed_start,
        projected_start_date=actual_start_date,
        original_actual_start_date=control["original_actual_start_date"],
        deposit_settlement_identity=control["settlement_identity"],
        source_event_id=int(control["current_event_id"]),
        schedule_adjustment_receipt_id=adjustment_receipt_id,
    )
    try:
        apply_order_lifecycle_control_command(cursor, envelope, command)
    except OrderLifecycleControlConcurrencyError as error:
        raise RuntimeError("order_version_conflict") from error


_SELECT_ADJUSTMENT_RECONFIRMATION_SQL = """
    SELECT control.current_event_id, control.confirmed_start_date,
           JSON_UNQUOTE(JSON_EXTRACT(event.payload_snapshot, '$.original_actual_start_date')) AS original_actual_start_date,
           settlement.settlement_identity,
           (event.action = 'clear'
            AND JSON_UNQUOTE(JSON_EXTRACT(event.payload_snapshot, '$.new_actual_start_date')) = CAST(control.confirmed_start_date AS CHAR)
            AND settlement.settlement_state = 'settled'
            AND JSON_UNQUOTE(JSON_EXTRACT(event.payload_snapshot, '$.deposit_settlement_identity')) = settlement.settlement_identity
            AND control.deposit_settlement_identity_hash = SHA2(settlement.settlement_identity, 256)) AS source_matches_current_settlement
    FROM order_lifecycle_control_state AS control
    JOIN order_lifecycle_control_events AS event
      ON event.id = control.current_event_id AND event.case_no = control.case_no
     AND event.control_type = control.control_type AND event.control_key = control.control_key
    LEFT JOIN client_deposit_settlement_projection AS settlement ON settlement.case_no = control.case_no
    WHERE control.case_no = %s AND control.control_type = 'actual_start_reconfirmation'
      AND control.control_key = 'actual_start_reconfirmation' AND control.state = 'cleared'
    FOR UPDATE
"""


def _append_lifecycle_event(cursor, command, snapshot):
    cursor.execute(
        _LIFECYCLE_EVENT_INSERT_SQL,
        (
            command.candidate.case_no,
            command.trigger_event,
            command.candidate.before_status.value,
            command.candidate.after_status.value,
            command.actor.actor_id,
            command.candidate.business_date,
            command.expected_order_version,
            _child_identity(command, "lifecycle-event"),
            snapshot,
        ),
    )
    return int(cursor.lastrowid)


def _forms_service_data_lock(command):
    return (
        command.candidate.service_data_lock_should_exist
        and not command.candidate.service_data_lock_was_present
    )


def _insert_service_data_lock(cursor, command, lifecycle_event_id):
    if command.client_settlement_fingerprint is None:
        raise ValueError("client_settlement_fingerprint_required")
    cursor.execute(
        "INSERT INTO order_service_data_locks "
        "(case_no,lifecycle_event_id,client_settlement_fingerprint,created_by) "
        "VALUES (%s,%s,%s,%s)",
        (
            command.candidate.case_no,
            lifecycle_event_id,
            command.client_settlement_fingerprint.value,
            command.actor.actor_id,
        ),
    )


def _append_orders_outbox(cursor, command, lifecycle_event_id, snapshot):
    cursor.execute(
        "INSERT INTO orders_domain_outbox "
        "(case_no,lifecycle_event_id,intent_key,intent_type,payload_snapshot) "
        "VALUES (%s,%s,%s,'lifecycle_projection_changed',%s)",
        (
            command.candidate.case_no,
            lifecycle_event_id,
            _child_identity(command, "orders-outbox"),
            snapshot,
        ),
    )


def _lifecycle_payload(command):
    candidate = command.candidate
    return {
        "actual_start_date": str(command.actual_start_date) if getattr(command, 'actual_start_date', None) else None,
        "staff_payment_due_date": (
            command.staff_payment_due_date.isoformat()
            if getattr(command, "staff_payment_due_date", None) is not None else None
        ),
        "actual_end_date": (
            candidate.actual_end_date.isoformat()
            if candidate.actual_end_date is not None
            else None
        ),
        "after_status": candidate.after_status.value,
        "alert_codes": candidate.alert_codes,
        "before_status": candidate.before_status.value,
        "completion_instant": (
            candidate.completion_instant.isoformat()
            if candidate.completion_instant is not None
            else None
        ),
        "correlation_id": command.correlation_id.value,
        "reason": command.reason,
        "resulting_order_version": command.resulting_order_version,
        "service_completion_reached": candidate.service_completion_reached,
        "service_data_lock_should_exist": (
            candidate.service_data_lock_should_exist
        ),
    }


def _child_identity(command, purpose):
    return "child:" + fingerprint_payload(
        {
            "outer_key": command.idempotency_key.value,
            "domain": "orders",
            "purpose": purpose,
        }
    ).value


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


_LIFECYCLE_EVENT_INSERT_SQL = (
    "INSERT INTO order_lifecycle_state_events "
    "(case_no,trigger_event,before_status,after_status,actor,business_date,"
    "expected_version,idempotency_key,facts_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_ORDER_PROJECTION_UPDATE_SQL = (
    "UPDATE orders SET status=%s,actual_end_date=%s,actual_start_date=COALESCE(%s,actual_start_date),"
    "staff_payment_due_date=COALESCE(staff_payment_due_date,%s),lifecycle_version=%s "
    "WHERE case_no=%s AND lifecycle_version=%s"
)

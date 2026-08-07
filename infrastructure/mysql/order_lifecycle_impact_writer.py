"""MySQL writer for the typed lifecycle impact inside Orders Terms Apply."""

from __future__ import annotations

import json

from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.terms_workflow import (
    LifecycleImpactPersistenceCommand,
)


def persist_order_lifecycle_impact(cursor, command) -> int:
    lifecycle_event_id = _append_lifecycle_event(cursor, command)
    if _forms_service_data_lock(command):
        _insert_service_data_lock(cursor, command, lifecycle_event_id)
    _append_orders_outbox(cursor, command, lifecycle_event_id)
    return lifecycle_event_id


def _append_lifecycle_event(cursor, command):
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
            _canonical_json(_lifecycle_payload(command)),
        ),
    )
    return int(cursor.lastrowid)


def _forms_service_data_lock(command):
    return (
        command.candidate.service_data_lock_should_exist
        and not command.candidate.service_data_lock_was_present
    )


def _insert_service_data_lock(cursor, command, lifecycle_event_id):
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


def _append_orders_outbox(cursor, command, lifecycle_event_id):
    cursor.execute(
        "INSERT INTO orders_domain_outbox "
        "(case_no,lifecycle_event_id,intent_key,intent_type,payload_snapshot) "
        "VALUES (%s,%s,%s,'lifecycle_projection_changed',%s)",
        (
            command.candidate.case_no,
            lifecycle_event_id,
            _child_identity(command, "orders-outbox"),
            _canonical_json(_lifecycle_payload(command)),
        ),
    )


def _lifecycle_payload(command):
    candidate = command.candidate
    return {
        "actual_end_date": candidate.actual_end_date.isoformat(),
        "after_status": candidate.after_status.value,
        "alert_codes": candidate.alert_codes,
        "before_status": candidate.before_status.value,
        "completion_instant": candidate.completion_instant.isoformat(),
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

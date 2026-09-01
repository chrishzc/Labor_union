"""MySQL persistence adapter for the Orders Cancellation transaction."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
import json
from typing import Any

from pymysql.err import IntegrityError

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.scheduling.availability_lock_cancellation_workflow import (
    cancel_caregiver_availability_lock_for_order,
)
from subsystems.orders.order_lifecycle_command_envelope import (
    lock_order_lifecycle_command_envelope,
)
from subsystems.orders.order_lifecycle_control_commands import (
    CancellationControlCommand,
    apply_order_lifecycle_control_command,
)
from subsystems.orders.cancellation_workflow import (
    CancellationOrderPersistenceCommand,
    CancellationReceiptPersistenceCommand,
    OrderCancellationApplyRequest,
    OrderCancellationPreview,
    OrderCancellationReceipt,
    StoredCancellationReceipt,
)
from subsystems.orders.terms_workflow import CommandClaimState

from .client_finance_terms_writer import persist_client_finance_terms_impact
from .order_cancellation_read_model import (
    cancellation_preflight_staff_ids,
    list_caregiver_options,
    load_cancellation_locked_facts,
    load_cancellation_preview_facts,
)
from .payroll_terms_writer import persist_payroll_terms_impact
from .scheduling_replacement_writer import persist_scheduling_replacement

_COMMAND_FAMILY = "orders_cancellation"


class MySqlOrderCancellationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_for_preview(self, case_no, requested_staff_ids):
        with self._connection.cursor() as cursor:
            return load_cancellation_preview_facts(
                cursor, case_no, requested_staff_ids
            )

    def list_caregiver_options(self, case_no):
        with self._connection.cursor() as cursor:
            return list_caregiver_options(cursor, case_no)

    def preflight_impacted_staff_ids(self, case_no, requested_staff_ids):
        with self._connection.cursor() as cursor:
            return cancellation_preflight_staff_ids(
                cursor, case_no, requested_staff_ids
            )

    def load_for_apply(self, case_no, preflight_staff_ids):
        with self._connection.cursor() as cursor:
            return load_cancellation_locked_facts(
                cursor, case_no, preflight_staff_ids
            )

    def find_receipt(self, key, *, for_update):
        lock_clause = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL + lock_clause, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def claim_command(self, request, command_fingerprint):
        with self._connection.cursor() as cursor:
            if _insert_claim(cursor, request, command_fingerprint):
                return CommandClaimState.CREATED
            claim_row = _lock_claim(cursor, request.idempotency_key)
        return _claim_state(request, command_fingerprint, claim_row)

    def append_cancellation_event(self, request, preview):
        with self._connection.cursor() as cursor:
            cursor.execute(_EVENT_INSERT_SQL, _event_values(request, preview))
            return int(cursor.lastrowid)

    def cancel_waiting_deposit_lock(self, request, cancellation_event_id):
        with self._connection.cursor() as cursor:
            _require_cancellation_event(cursor, request, cancellation_event_id)
            envelope = lock_order_lifecycle_command_envelope(
                cursor,
                request.case_no,
                request.expected_order_version.value,
                request.idempotency_key.value,
            )
            cancel_caregiver_availability_lock_for_order(
                cursor,
                envelope,
                request.case_no,
                request.idempotency_key.value,
                request.actor.actor_id,
                request.reason,
            )

    def replace_scheduling_generation(self, command):
        with self._connection.cursor() as cursor:
            return persist_scheduling_replacement(cursor, command)

    def persist_client_finance_impact(self, command):
        with self._connection.cursor() as cursor:
            persist_client_finance_terms_impact(cursor, command)

    def persist_payroll_impact(self, command):
        with self._connection.cursor() as cursor:
            persist_payroll_terms_impact(cursor, command)

    # Kept cohesive because the envelope and control must use one cursor.
    def activate_cancellation_control(self, request, cancellation_event_id):
        with self._connection.cursor() as cursor:
            _require_cancellation_event(cursor, request, cancellation_event_id)
            envelope = lock_order_lifecycle_command_envelope(
                cursor,
                request.case_no,
                request.expected_order_version.value,
                request.idempotency_key.value,
            )
            result = apply_order_lifecycle_control_command(
                cursor,
                envelope,
                CancellationControlCommand(
                    "activate",
                    request.actor.actor_id,
                    request.reason,
                    request.expected_order_version.value,
                    request.idempotency_key.value,
                ),
            )
        return result.event_id

    def persist_cancellation_lifecycle(
        self,
        request,
        preview,
        cancellation_control_event_id,
    ):
        with self._connection.cursor() as cursor:
            _require_control_event(
                cursor, request, cancellation_control_event_id
            )
            event_id = _insert_lifecycle_event(cursor, request, preview)
            _append_lifecycle_outbox(cursor, request, preview, event_id)
            return event_id

    def update_cancelled_order(self, command):
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_UPDATE_SQL, _order_update_values(command))
            if cursor.rowcount != 1:
                raise RuntimeError("order_version_conflict")

    def save_receipt(self, command):
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_INSERT_SQL, _receipt_values(command))
            if cursor.rowcount != 1:
                raise RuntimeError("cancellation_receipt_not_saved")


def _insert_claim(cursor, request, command_fingerprint) -> bool:
    try:
        cursor.execute(
            "INSERT INTO application_command_claims "
            "(idempotency_key,command_family,aggregate_identity,"
            "command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)",
            (
                request.idempotency_key.value,
                _COMMAND_FAMILY,
                request.case_no,
                command_fingerprint.value,
                request.correlation_id.value,
            ),
        )
    except IntegrityError as error:
        if _mysql_error_code(error) != 1062:
            raise
        return False
    return True


def _lock_claim(cursor, key):
    cursor.execute(
        "SELECT command_family,aggregate_identity,command_fingerprint "
        "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
        (key.value,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("idempotency_claim_missing")
    return row


def _claim_state(request, command_fingerprint, row):
    expected = (
        _COMMAND_FAMILY,
        request.case_no,
        command_fingerprint.value,
    )
    actual = (
        str(row["command_family"]),
        str(row["aggregate_identity"]),
        str(row["command_fingerprint"]),
    )
    if actual == expected:
        return CommandClaimState.MATCHED
    return CommandClaimState.MISMATCH


# Kept cohesive because these values are one immutable event row identity.
def _event_values(request, preview):
    candidate = preview.candidate
    confirmed_days = tuple(
        {
            "reason": item.reason,
            "service_date": item.service_date.isoformat(),
            "staff_id": item.staff_id,
        }
        for item in candidate.confirmed_service_days
    )
    return (
        request.case_no,
        candidate.cancellation_date,
        candidate.actual_end_date,
        candidate.official_service_day_count,
        candidate.official_service_hours,
        _canonical_json(confirmed_days),
        preview.order_version,
        preview.order_version + 1,
        preview.fingerprint.value,
        request.idempotency_key.value,
        request.actor.actor_id,
        request.reason,
        request.correlation_id.value,
    )


def _require_cancellation_event(cursor, request, event_id) -> None:
    cursor.execute(
        "SELECT id FROM order_cancellation_events "
        "WHERE id=%s AND case_no=%s AND idempotency_key=%s FOR UPDATE",
        (event_id, request.case_no, request.idempotency_key.value),
    )
    if cursor.fetchone() is None:
        raise RuntimeError("cancellation_event_not_found")


def _require_control_event(cursor, request, event_id) -> None:
    cursor.execute(
        "SELECT id FROM order_lifecycle_control_events "
        "WHERE id=%s AND case_no=%s AND control_type='cancellation' "
        "AND action='activate' AND idempotency_key=%s FOR UPDATE",
        (event_id, request.case_no, request.idempotency_key.value),
    )
    if cursor.fetchone() is None:
        raise RuntimeError("cancellation_control_event_not_found")


def _insert_lifecycle_event(cursor, request, preview):
    source_subject = _line_user_id(cursor, request.case_no)
    cursor.execute(
        _LIFECYCLE_EVENT_INSERT_SQL,
        _lifecycle_values(request, preview, source_subject),
    )
    return int(cursor.lastrowid)


def _lifecycle_values(request, preview, source_subject):
    impact = preview.lifecycle_impact
    facts = _lifecycle_facts(request, preview)
    if impact.after_status is OrderLifecycleStatus.CANCELLED:
        facts.update(_terminal_closure_fields(request, preview, None, source_subject))
    return (
        request.case_no,
        "order_cancellation_applied",
        impact.before_status.value,
        impact.after_status.value,
        request.actor.actor_id,
        preview.candidate.cancellation_date,
        preview.order_version,
        request.idempotency_key.value,
        _canonical_json(facts),
    )


def _lifecycle_facts(request, preview):
    candidate = preview.candidate
    return {
        "actual_start_date": _optional_iso_date(candidate.actual_start_date),
        "actual_end_date": _optional_iso_date(candidate.actual_end_date),
        "cancellation": True,
        "cancellation_event_fingerprint": candidate.fingerprint.value,
        "cancellation_reason": request.reason,
        "official_service_day_count": candidate.official_service_day_count,
        "official_service_hours": candidate.official_service_hours,
    }


def _append_lifecycle_outbox(cursor, request, preview, event_id):
    payload = {
        "actual_start_date": _optional_iso_date(
            preview.candidate.actual_start_date
        ),
        "actual_end_date": _optional_iso_date(
            preview.lifecycle_impact.actual_end_date
        ),
        "after_status": preview.lifecycle_impact.after_status.value,
        "correlation_id": request.correlation_id.value,
        "resulting_order_version": preview.order_version + 1,
    }
    if preview.lifecycle_impact.after_status is OrderLifecycleStatus.CANCELLED:
        payload.update(
            _terminal_closure_fields(
                request, preview, event_id, _line_user_id(cursor, request.case_no)
            )
        )
    cursor.execute(
        "INSERT INTO orders_domain_outbox "
        "(case_no,lifecycle_event_id,intent_key,intent_type,payload_snapshot) "
        "VALUES (%s,%s,%s,'lifecycle_projection_changed',%s)",
        (
            request.case_no,
            event_id,
            _child_identity(request, "orders-outbox"),
            _canonical_json(payload),
        ),
    )


def _line_user_id(cursor, case_no):
    cursor.execute(
        "SELECT c.line_user_id FROM orders o JOIN clients c ON c.id=o.client_id "
        "WHERE o.case_no=%s",
        (case_no,),
    )
    row = cursor.fetchone() or {}
    return row.get("line_user_id") or None


def _terminal_closure_fields(request, preview, event_id, source_subject):
    version = preview.order_version + 1
    identity = f"case-terminal:{request.case_no}:cancellation:{version}"
    return {
        "event_type": "case_terminal_closure",
        "source_event_identity": identity,
        "terminal_kind": "cancellation",
        "source_subject": source_subject,
        "producer_reference": f"orders.lifecycle_event:{request.case_no}:{version}",
        "occurred_at": preview.candidate.cancellation_date.isoformat() + "T00:00:00+00:00",
        "idempotency_identity": identity,
    }


def _child_identity(request, purpose):
    return "child:" + fingerprint_payload(
        {
            "domain": "orders",
            "outer_key": request.idempotency_key.value,
            "purpose": purpose,
        }
    ).value


def _order_update_values(command):
    return (
        command.actual_start_date,
        command.actual_end_date,
        command.lifecycle_status.value,
        command.resulting_order_version,
        command.case_no,
        command.expected_order_version,
    )


# Kept cohesive because these values are one immutable receipt row identity.
def _receipt_values(command):
    receipt = command.stored_receipt.receipt
    return (
        command.key.value,
        command.stored_receipt.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        receipt.case_no,
        command.cancellation_event_id,
        command.scheduling_receipt_id,
        command.cancellation_control_event_id,
        command.lifecycle_event_id,
        receipt.order_version,
        receipt.scheduling_version,
        receipt.scheduling_generation,
        receipt.client_finance_version,
        receipt.payroll_version,
        receipt.lifecycle_status.value,
        receipt.actual_end_date,
        receipt.official_service_day_count,
        receipt.official_service_hours,
        command.correlation_id.value,
        _canonical_json(_receipt_payload(receipt)),
    )


# Kept cohesive because exact receipt restoration is one integrity boundary.
def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    _require_exact_receipt_keys(payload)
    receipt = OrderCancellationReceipt(
        _required_text(payload, "case_no"),
        _required_integer(payload, "order_version"),
        _required_integer(payload, "scheduling_version"),
        _required_integer(payload, "scheduling_generation"),
        _required_integer(payload, "client_finance_version"),
        _required_integer(payload, "payroll_version"),
        _lifecycle_status(payload),
        _optional_date(payload, "actual_end_date"),
        _required_integer(payload, "official_service_day_count"),
        _required_integer(payload, "official_service_hours"),
        _integer_tuple(payload, "cancelled_assignment_ids"),
        _text_tuple(payload, "created_assignment_keys"),
        PreviewFingerprint(_required_text(payload, "preview_fingerprint")),
    )
    _validate_receipt_columns(row, receipt)
    return StoredCancellationReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _receipt_payload(receipt):
    return {
        "actual_end_date": _optional_iso_date(receipt.actual_end_date),
        "cancelled_assignment_ids": receipt.cancelled_assignment_ids,
        "case_no": receipt.case_no,
        "client_finance_version": receipt.client_finance_version,
        "created_assignment_keys": receipt.created_assignment_keys,
        "lifecycle_status": receipt.lifecycle_status.value,
        "official_service_day_count": receipt.official_service_day_count,
        "official_service_hours": receipt.official_service_hours,
        "order_version": receipt.order_version,
        "payroll_version": receipt.payroll_version,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "scheduling_generation": receipt.scheduling_generation,
        "scheduling_version": receipt.scheduling_version,
    }


# Kept cohesive because every duplicated receipt column must compare atomically.
def _validate_receipt_columns(row, receipt) -> None:
    expected = (
        receipt.case_no,
        receipt.order_version,
        receipt.scheduling_version,
        receipt.scheduling_generation,
        receipt.client_finance_version,
        receipt.payroll_version,
        receipt.lifecycle_status.value,
        receipt.actual_end_date,
        receipt.official_service_day_count,
        receipt.official_service_hours,
        receipt.preview_fingerprint.value,
    )
    actual = (
        str(row["case_no"]),
        int(row["order_version"]),
        int(row["scheduling_version"]),
        int(row["scheduling_generation"]),
        int(row["client_finance_version"]),
        int(row["payroll_version"]),
        str(row["lifecycle_status"]),
        row["actual_end_date"],
        int(row["official_service_day_count"]),
        int(row["official_service_hours"]),
        str(row["preview_fingerprint"]),
    )
    if actual != expected:
        raise ValueError("order_cancellation_receipt_integrity_violation")


def _require_exact_receipt_keys(payload) -> None:
    if set(payload) != _RECEIPT_PAYLOAD_KEYS:
        raise ValueError("order_cancellation_receipt_integrity_violation")


def _required_text(payload, key):
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("order_cancellation_receipt_integrity_violation")
    return value


def _required_integer(payload, key):
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("order_cancellation_receipt_integrity_violation")
    return value


def _optional_date(payload, key):
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("order_cancellation_receipt_integrity_violation")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            "order_cancellation_receipt_integrity_violation"
        ) from error


def _lifecycle_status(payload):
    try:
        return OrderLifecycleStatus(
            _required_text(payload, "lifecycle_status")
        )
    except ValueError as error:
        raise ValueError(
            "order_cancellation_receipt_integrity_violation"
        ) from error


def _integer_tuple(payload, key):
    values = payload[key]
    if not isinstance(values, list):
        raise ValueError("order_cancellation_receipt_integrity_violation")
    result = tuple(values)
    if any(not isinstance(value, int) or value <= 0 for value in result):
        raise ValueError("order_cancellation_receipt_integrity_violation")
    return result


def _text_tuple(payload, key):
    values = payload[key]
    if not isinstance(values, list):
        raise ValueError("order_cancellation_receipt_integrity_violation")
    result = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError("order_cancellation_receipt_integrity_violation")
    return result


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("receipt snapshot must be an object")
    return parsed


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _optional_iso_date(value):
    return None if value is None else value.isoformat()


def _mysql_error_code(error):
    return error.args[0] if error.args and isinstance(error.args[0], int) else None


_EVENT_INSERT_SQL = (
    "INSERT INTO order_cancellation_events "
    "(case_no,cancellation_date,actual_end_date,official_service_day_count,"
    "official_service_hours,confirmed_service_days,expected_order_version,"
    "resulting_order_version,preview_fingerprint,idempotency_key,actor,"
    "reason,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_LIFECYCLE_EVENT_INSERT_SQL = (
    "INSERT INTO order_lifecycle_state_events "
    "(case_no,trigger_event,before_status,after_status,actor,business_date,"
    "expected_version,idempotency_key,facts_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_ORDER_UPDATE_SQL = (
    "UPDATE orders SET actual_start_date=%s,actual_end_date=%s,status=%s,"
    "lifecycle_version=%s WHERE case_no=%s AND lifecycle_version=%s"
)

_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,case_no,order_version,"
    "scheduling_version,scheduling_generation,client_finance_version,"
    "payroll_version,lifecycle_status,actual_end_date,"
    "official_service_day_count,official_service_hours,result_snapshot "
    "FROM order_cancellation_apply_receipts WHERE idempotency_key=%s"
)

_RECEIPT_INSERT_SQL = (
    "INSERT INTO order_cancellation_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "cancellation_event_id,scheduling_command_receipt_id,"
    "cancellation_control_event_id,lifecycle_event_id,order_version,"
    "scheduling_version,scheduling_generation,client_finance_version,"
    "payroll_version,lifecycle_status,actual_end_date,"
    "official_service_day_count,official_service_hours,correlation_id,"
    "result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_RECEIPT_PAYLOAD_KEYS = {
    "actual_end_date",
    "cancelled_assignment_ids",
    "case_no",
    "client_finance_version",
    "created_assignment_keys",
    "lifecycle_status",
    "official_service_day_count",
    "official_service_hours",
    "order_version",
    "payroll_version",
    "preview_fingerprint",
    "scheduling_generation",
    "scheduling_version",
}


__all__ = ["MySqlOrderCancellationRepository"]

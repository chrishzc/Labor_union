"""MySQL persistence adapter for the Actual Start outer transaction."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from pymysql.err import IntegrityError

from domains.orders.actual_start import (
    ActualStartCandidateKind,
    ActualStartReconfirmationAction,
    ActualStartReconfirmationFacts,
    ActualStartReconfirmationState,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.order_lifecycle_command_envelope import (
    lock_order_lifecycle_command_envelope,
)
from subsystems.orders.order_lifecycle_control_commands import (
    ActualStartReconfirmationConfirmedCommand,
    apply_order_lifecycle_control_command,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.orders.actual_start_workflow import (
    ActualStartApplyRequest,
    ActualStartPersistenceCommand,
    ActualStartPreview,
    ActualStartReceiptPersistenceCommand,
    ActualStartWorkflowContext,
    ConfirmActualStartReconfirmationCommand,
)
from subsystems.orders.terms_workflow import (
    ClientFinanceImpactPersistenceCommand,
    CommandClaimState,
    LifecycleImpactPersistenceCommand,
    OrderTermsReceipt,
    PayrollImpactPersistenceCommand,
    SchedulingReplacementCommand,
    SchedulingReplacementResult,
    StoredTermsReceipt,
)

from .client_finance_terms_writer import persist_client_finance_terms_impact
from .order_lifecycle_impact_writer import persist_order_lifecycle_impact
from .order_terms_read_model import (
    load_locked_facts,
    load_preview_facts,
    preflight_staff_ids,
)
from .payroll_terms_writer import persist_payroll_terms_impact
from .scheduling_replacement_writer import persist_scheduling_replacement

_COMMAND_FAMILY = "orders_actual_start"


class MySqlOrderActualStartRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_for_preview(self, case_no: str) -> ActualStartWorkflowContext:
        with self._connection.cursor() as cursor:
            shared_facts = load_preview_facts(cursor, case_no)
            reconfirmation = _load_reconfirmation_facts(
                cursor,
                case_no,
                lock=False,
            )
        return ActualStartWorkflowContext(shared_facts, reconfirmation)

    def preflight_impacted_staff_ids(self, case_no: str) -> tuple[int, ...]:
        with self._connection.cursor() as cursor:
            return preflight_staff_ids(cursor, case_no)

    def load_for_apply(
        self,
        case_no: str,
        preflight_staff_ids: tuple[int, ...],
    ) -> ActualStartWorkflowContext:
        with self._connection.cursor() as cursor:
            shared_facts = load_locked_facts(
                cursor,
                case_no,
                preflight_staff_ids,
            )
            reconfirmation = _load_reconfirmation_facts(
                cursor,
                case_no,
                lock=True,
            )
        return ActualStartWorkflowContext(shared_facts, reconfirmation)

    def claim_actual_start_command(
        self,
        request: ActualStartApplyRequest,
        command_fingerprint: PreviewFingerprint,
    ) -> CommandClaimState:
        with self._connection.cursor() as cursor:
            if _insert_claim(cursor, request, command_fingerprint):
                return CommandClaimState.CREATED
            claim_row = _lock_claim(cursor, request.idempotency_key)
        return _claim_state(request, command_fingerprint, claim_row)

    def find_actual_start_receipt(
        self,
        key: IdempotencyKey,
        *,
        for_update: bool,
    ) -> StoredTermsReceipt | None:
        lock_clause = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL + lock_clause, (key.value,))
            receipt_row = cursor.fetchone()
        return None if receipt_row is None else _stored_receipt(receipt_row)

    def append_actual_start_event(
        self,
        request: ActualStartApplyRequest,
        preview: ActualStartPreview,
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(_EVENT_INSERT_SQL, _event_values(request, preview))
            return int(cursor.lastrowid)

    def replace_scheduling_generation(
        self,
        command: SchedulingReplacementCommand,
    ) -> SchedulingReplacementResult:
        with self._connection.cursor() as cursor:
            return persist_scheduling_replacement(cursor, command)

    def persist_client_finance_impact(
        self,
        command: ClientFinanceImpactPersistenceCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            persist_client_finance_terms_impact(cursor, command)

    def persist_payroll_impact(
        self,
        command: PayrollImpactPersistenceCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            persist_payroll_terms_impact(cursor, command)

    def confirm_actual_start_reconfirmation(
        self,
        command: ConfirmActualStartReconfirmationCommand,
    ) -> int:
        with self._connection.cursor() as cursor:
            _require_current_reconfirmation_matches(cursor, command)
            event = _locked_actual_start_event(cursor, command)
            envelope = lock_order_lifecycle_command_envelope(
                cursor,
                command.case_no,
                int(event["expected_order_version"]),
                command.idempotency_key.value,
            )
            result = apply_order_lifecycle_control_command(
                cursor,
                envelope,
                _control_confirmation_command(command, event),
            )
        return result.event_id

    def persist_lifecycle_impact(
        self,
        command: LifecycleImpactPersistenceCommand,
    ) -> int:
        with self._connection.cursor() as cursor:
            return persist_order_lifecycle_impact(cursor, command)

    def update_actual_start(
        self,
        command: ActualStartPersistenceCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_UPDATE_SQL, _order_update_values(command))
            if cursor.rowcount != 1:
                raise RuntimeError("order_version_conflict")

    def save_actual_start_receipt(
        self,
        command: ActualStartReceiptPersistenceCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_INSERT_SQL, _receipt_values(command))
            if cursor.rowcount != 1:
                raise RuntimeError("actual_start_event_not_found")


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


def _load_reconfirmation_facts(
    cursor, case_no: str, *, lock: bool
) -> ActualStartReconfirmationFacts | None:
    projection = _select_deposit_settlement_projection(cursor, case_no, lock)
    control = _select_actual_start_control(cursor, case_no, lock)
    state, required_identity = _control_reconfirmation_facts(control)
    if projection is None:
        return _facts_without_settlement_projection(
            state,
            required_identity,
        )
    deposit_settled, current_identity = _deposit_settlement_facts(projection)
    return ActualStartReconfirmationFacts(
        state=state,
        required_settlement_identity=required_identity,
        current_settlement_identity=current_identity,
        deposit_settled=deposit_settled,
    )


def _facts_without_settlement_projection(state, required_identity):
    if state is ActualStartReconfirmationState.ACTIVE:
        return None
    return ActualStartReconfirmationFacts(
        state=state,
        required_settlement_identity=required_identity,
        current_settlement_identity=None,
        deposit_settled=False,
    )


def _select_deposit_settlement_projection(cursor, case_no, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_DEPOSIT_SETTLEMENT_SELECT_SQL + lock_clause, (case_no,))
    row = cursor.fetchone()
    if row is not None and not isinstance(row, Mapping):
        raise ValueError("deposit_settlement_projection_invalid")
    return row


def _select_actual_start_control(cursor, case_no, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_ACTUAL_START_CONTROL_SELECT_SQL + lock_clause, (case_no,))
    row = cursor.fetchone()
    if row is not None and not isinstance(row, Mapping):
        raise ValueError("actual_start_reconfirmation_control_invalid")
    return row


def _deposit_settlement_facts(projection):
    state = str(projection["settlement_state"])
    if state not in {"settled", "unsettled"}:
        raise ValueError("deposit_settlement_state_invalid")
    identity = _optional_fingerprint(projection["settlement_identity"])
    if (state == "settled") != (identity is not None):
        raise ValueError("deposit_settlement_projection_invalid")
    return state == "settled", identity


def _control_reconfirmation_facts(control):
    if control is None:
        return ActualStartReconfirmationState.NOT_REQUIRED, None
    state = str(control["state"])
    action = str(control["action"])
    expected_action = {"active": "activate", "cleared": "clear"}.get(state)
    if action != expected_action:
        raise ValueError("actual_start_reconfirmation_control_invalid")
    if state == "active":
        payload = _json_object(control["payload_snapshot"])
        required = _required_fingerprint(
            payload.get("deposit_settlement_identity")
        )
        return ActualStartReconfirmationState.ACTIVE, required
    if state == "cleared":
        required = _required_fingerprint(
            control["deposit_settlement_identity_hash"]
        )
        return ActualStartReconfirmationState.CLEARED, required
    raise ValueError("actual_start_reconfirmation_control_invalid")


def _optional_fingerprint(value):
    if value is None:
        return None
    return _required_fingerprint(value)


def _required_fingerprint(value):
    if not isinstance(value, str):
        raise ValueError("settlement_identity_invalid")
    return PreviewFingerprint(value)


def _require_current_reconfirmation_matches(cursor, command):
    facts = _load_reconfirmation_facts(cursor, command.case_no, lock=True)
    matches = (
        facts is not None
        and facts.state is ActualStartReconfirmationState.ACTIVE
        and facts.deposit_settled
        and facts.required_settlement_identity
        == command.required_settlement_identity
        and facts.current_settlement_identity
        == command.required_settlement_identity
    )
    if not matches:
        raise RuntimeError("actual_start_reconfirmation_conflict")


def _locked_actual_start_event(cursor, command):
    cursor.execute(
        _ACTUAL_START_EVENT_LOCK_SQL,
        (
            command.actual_start_event_id,
            command.case_no,
            command.idempotency_key.value,
        ),
    )
    event = cursor.fetchone()
    if not isinstance(event, Mapping):
        raise RuntimeError("actual_start_reconfirmation_event_not_found")
    _validate_delayed_reconfirmation_event(command, event)
    return event


def _validate_delayed_reconfirmation_event(command, event):
    if (
        str(event["event_type"])
        != "reconfirmed_after_delayed_settlement"
        or event["before_actual_start_date"] is None
        or str(event["deposit_settlement_identity"])
        != command.required_settlement_identity.value
    ):
        raise RuntimeError("actual_start_reconfirmation_event_invalid")


def _control_confirmation_command(command, event):
    return ActualStartReconfirmationConfirmedCommand(
        actor=command.actor.actor_id,
        reason=command.reason,
        expected_version=int(event["expected_order_version"]),
        idempotency_key=command.idempotency_key.value,
        original_actual_start_date=event["before_actual_start_date"],
        new_actual_start_date=event["after_actual_start_date"],
        deposit_settlement_identity=(
            command.required_settlement_identity.value
        ),
        preview_request_hash=command.reconfirmation_fingerprint.value,
        assignment_apply_receipt={
            "actual_start_event_id": command.actual_start_event_id,
            "correlation_id": command.correlation_id.value,
        },
    )


def _lock_claim(cursor, key):
    cursor.execute(
        "SELECT command_family,aggregate_identity,command_fingerprint "
        "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
        (key.value,),
    )
    claim_row = cursor.fetchone()
    if not isinstance(claim_row, Mapping):
        raise RuntimeError("idempotency_claim_missing")
    return claim_row


def _claim_state(request, command_fingerprint, claim_row):
    expected = (_COMMAND_FAMILY, request.case_no, command_fingerprint.value)
    actual = (
        str(claim_row["command_family"]),
        str(claim_row["aggregate_identity"]),
        str(claim_row["command_fingerprint"]),
    )
    if actual == expected:
        return CommandClaimState.MATCHED
    return CommandClaimState.MISMATCH


def _event_values(request, preview):
    event_type = _event_type(preview)
    settlement_identity = _event_settlement_identity(preview)
    return (
        request.case_no,
        event_type,
        preview.before_actual_start_date,
        preview.after_actual_start_date,
        settlement_identity,
        preview.order_version,
        preview.order_version + 1,
        preview.fingerprint.value,
        request.idempotency_key.value,
        request.actor.actor_id,
        request.reason,
        request.correlation_id.value,
    )


def _event_type(preview):
    if (
        preview.reconfirmation.action
        is ActualStartReconfirmationAction.CONFIRM_ACTIVE
    ):
        return "reconfirmed_after_delayed_settlement"
    if preview.actual_start.kind is ActualStartCandidateKind.FIRST_CONFIRMATION:
        return "confirmed"
    if preview.actual_start.kind is ActualStartCandidateKind.CORRECTION:
        return "corrected"
    raise ValueError("unsupported_actual_start_event_kind")


def _event_settlement_identity(preview):
    identity = preview.reconfirmation.settlement_identity
    if (
        preview.reconfirmation.action
        is ActualStartReconfirmationAction.CONFIRM_ACTIVE
    ):
        if identity is None:
            raise ValueError("active_reconfirmation_identity_missing")
        return identity.value
    if identity is not None:
        raise ValueError("unexpected_reconfirmation_identity")
    return None


def _order_update_values(command):
    status = command.lifecycle_status
    if not isinstance(status, OrderLifecycleStatus):
        raise TypeError("lifecycle_status must be OrderLifecycleStatus")
    return (
        command.actual_start_date,
        command.actual_end_date,
        command.staff_payment_due_date,
        status.value,
        command.resulting_order_version,
        command.case_no,
        command.expected_order_version,
    )


# Kept cohesive so the SQL column order and receipt evidence cannot drift.
def _receipt_values(command):
    stored = command.stored_receipt
    receipt = stored.receipt
    return (
        command.key.value,
        stored.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        receipt.case_no,
        command.actual_start_event_id,
        command.scheduling_receipt_id,
        command.lifecycle_event_id,
        command.control_event_id,
        receipt.order_version,
        receipt.scheduling_version,
        receipt.scheduling_generation,
        receipt.client_finance_version,
        receipt.payroll_version,
        receipt.lifecycle_status.value,
        int(receipt.service_data_lock_formed),
        command.correlation_id.value,
        _canonical_json(_receipt_payload(receipt)),
        command.actual_start_event_id,
        receipt.case_no,
    )


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    _require_exact_receipt_keys(payload)
    receipt = _receipt_from_payload(payload)
    _validate_receipt_columns(row, receipt)
    return StoredTermsReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


# Kept cohesive so one validated snapshot creates one immutable receipt.
def _receipt_from_payload(payload):
    return OrderTermsReceipt(
        case_no=_required_text(payload, "case_no"),
        order_version=_required_integer(payload, "order_version"),
        scheduling_version=_required_integer(payload, "scheduling_version"),
        scheduling_generation=_required_integer(
            payload, "scheduling_generation"
        ),
        client_finance_version=_required_integer(
            payload, "client_finance_version"
        ),
        payroll_version=_required_integer(payload, "payroll_version"),
        lifecycle_status=_lifecycle_status(payload),
        service_data_lock_formed=_required_boolean(
            payload, "service_data_lock_formed"
        ),
        cancelled_assignment_ids=_integer_tuple(
            payload, "cancelled_assignment_ids"
        ),
        created_assignment_keys=_text_tuple(
            payload, "created_assignment_keys"
        ),
        official_service_day_count=_required_integer(
            payload, "official_service_day_count"
        ),
        official_service_hours=_required_integer(
            payload, "official_service_hours"
        ),
        preview_fingerprint=PreviewFingerprint(
            _required_text(payload, "preview_fingerprint")
        ),
    )


def _receipt_payload(receipt):
    return {
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
        "service_data_lock_formed": receipt.service_data_lock_formed,
    }


# Kept cohesive so indexed columns are compared as one integrity identity.
def _validate_receipt_columns(row, receipt):
    expected = (
        receipt.case_no,
        receipt.order_version,
        receipt.scheduling_version,
        receipt.scheduling_generation,
        receipt.client_finance_version,
        receipt.payroll_version,
        receipt.lifecycle_status.value,
        int(receipt.service_data_lock_formed),
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
        int(row["service_data_lock_formed"]),
        str(row["preview_fingerprint"]),
    )
    if actual != expected:
        raise ValueError("actual_start_receipt_integrity_violation")


def _require_exact_receipt_keys(payload):
    if set(payload) != _RECEIPT_PAYLOAD_KEYS:
        raise ValueError("actual_start_receipt_integrity_violation")


def _required_text(payload, key):
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("actual_start_receipt_integrity_violation")
    return value


def _required_integer(payload, key):
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("actual_start_receipt_integrity_violation")
    return value


def _required_boolean(payload, key):
    value = payload[key]
    if not isinstance(value, bool):
        raise ValueError("actual_start_receipt_integrity_violation")
    return value


def _lifecycle_status(payload):
    try:
        return OrderLifecycleStatus(_required_text(payload, "lifecycle_status"))
    except ValueError as error:
        raise ValueError("actual_start_receipt_integrity_violation") from error


def _integer_tuple(payload, key):
    values = payload[key]
    if not isinstance(values, list):
        raise ValueError("actual_start_receipt_integrity_violation")
    result = tuple(values)
    if any(not isinstance(value, int) or value <= 0 for value in result):
        raise ValueError("actual_start_receipt_integrity_violation")
    return result


def _text_tuple(payload, key):
    values = payload[key]
    if not isinstance(values, list):
        raise ValueError("actual_start_receipt_integrity_violation")
    result = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError("actual_start_receipt_integrity_violation")
    return result


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("actual_start receipt snapshot must be an object")
    return parsed


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _mysql_error_code(error):
    return error.args[0] if error.args and isinstance(error.args[0], int) else None


_EVENT_INSERT_SQL = (
    "INSERT INTO order_actual_start_events "
    "(case_no,event_type,before_actual_start_date,after_actual_start_date,"
    "deposit_settlement_identity,expected_order_version,"
    "resulting_order_version,preview_fingerprint,idempotency_key,actor,"
    "reason,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_ORDER_UPDATE_SQL = (
    "UPDATE orders SET actual_start_date=%s,actual_end_date=%s,"
    "staff_payment_due_date=COALESCE(staff_payment_due_date,%s),status=%s,"
    "lifecycle_version=%s WHERE case_no=%s AND lifecycle_version=%s"
)

_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,case_no,order_version,"
    "scheduling_version,scheduling_generation,client_finance_version,"
    "payroll_version,lifecycle_status,service_data_lock_formed,"
    "result_snapshot FROM order_actual_start_apply_receipts "
    "WHERE idempotency_key=%s"
)

_RECEIPT_INSERT_SQL = (
    "INSERT INTO order_actual_start_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "actual_start_event_id,scheduling_command_receipt_id,lifecycle_event_id,"
    "reconfirmation_control_event_id,order_version,scheduling_version,"
    "scheduling_generation,"
    "client_finance_version,payroll_version,lifecycle_status,"
    "actual_start_date,actual_end_date,service_data_lock_formed,"
    "correlation_id,result_snapshot) "
    "SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
    "actual_event.after_actual_start_date,orders.actual_end_date,%s,%s,%s "
    "FROM order_actual_start_events actual_event "
    "JOIN orders ON orders.case_no=actual_event.case_no "
    "WHERE actual_event.id=%s AND actual_event.case_no=%s"
)

_DEPOSIT_SETTLEMENT_SELECT_SQL = (
    "SELECT settlement_state,settlement_identity "
    "FROM client_deposit_settlement_projection WHERE case_no=%s"
)

_ACTUAL_START_CONTROL_SELECT_SQL = (
    "SELECT current_state.state,current_state.current_event_id,"
    "current_state.deposit_settlement_identity_hash,control_event.action,"
    "control_event.payload_snapshot "
    "FROM order_lifecycle_control_state current_state "
    "JOIN order_lifecycle_control_events control_event "
    "ON control_event.id=current_state.current_event_id "
    "AND control_event.case_no=current_state.case_no "
    "AND control_event.control_type=current_state.control_type "
    "AND control_event.control_key=current_state.control_key "
    "WHERE current_state.case_no=%s "
    "AND current_state.control_type='actual_start_reconfirmation' "
    "AND current_state.control_key='actual_start_reconfirmation'"
)

_ACTUAL_START_EVENT_LOCK_SQL = (
    "SELECT event_type,before_actual_start_date,after_actual_start_date,"
    "deposit_settlement_identity,expected_order_version "
    "FROM order_actual_start_events WHERE id=%s AND case_no=%s "
    "AND idempotency_key=%s FOR UPDATE"
)

_RECEIPT_PAYLOAD_KEYS = {
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
    "service_data_lock_formed",
}

__all__ = ["MySqlOrderActualStartRepository"]

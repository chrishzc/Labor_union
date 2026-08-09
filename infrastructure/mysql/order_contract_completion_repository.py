"""MySQL adapter for the Orders contract-completion transaction."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time, timedelta
import json
from typing import Any

from pymysql.err import IntegrityError

from domains.orders.contract_completion import (
    ContractCompletionFacts,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.terms import ServiceTimeTerms
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact,
)
from infrastructure.mysql.order_terms_read_model import (
    load_contract_client_finance_facts,
)
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionApplyRequest,
    ContractCompletionCommandClaimState,
    ContractCompletionClientFinanceCommand,
    ContractCompletionLifecycleEventCommand,
    ContractCompletionPreview,
    ContractCompletionProjectionCommand,
    ContractCompletionReceipt,
    ContractCompletionReceiptCommand,
    ContractCompletionWorkflowFacts,
    StoredContractCompletionReceipt,
)

_COMMAND_FAMILY = "orders_contract_completion"


class MySqlOrderContractCompletionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_for_preview(self, case_no: str) -> ContractCompletionFacts:
        with self._connection.cursor() as cursor:
            return _load_facts(cursor, case_no, lock=False)

    def load_for_apply(self, case_no: str) -> ContractCompletionFacts:
        with self._connection.cursor() as cursor:
            return _load_facts(cursor, case_no, lock=True)

    def claim_command(
        self,
        request: ContractCompletionApplyRequest,
        command_fingerprint: PreviewFingerprint,
    ) -> ContractCompletionCommandClaimState:
        with self._connection.cursor() as cursor:
            if _insert_claim(cursor, request, command_fingerprint):
                return ContractCompletionCommandClaimState.CREATED
            claim = _locked_claim(cursor, request.idempotency_key)
        return _claim_state(request, command_fingerprint, claim)

    def find_receipt(
        self,
        key: IdempotencyKey,
        *,
        for_update: bool,
    ) -> StoredContractCompletionReceipt | None:
        lock_clause = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL + lock_clause, (key.value,))
            row = cursor.fetchone()
        if row is None:
            return None
        return _stored_receipt(row)

    def append_contract_completion_event(
        self,
        request: ContractCompletionApplyRequest,
        preview: ContractCompletionPreview,
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CONTRACT_EVENT_INSERT_SQL,
                _contract_event_values(request, preview),
            )
            return int(cursor.lastrowid)

    def append_lifecycle_event(
        self,
        command: ContractCompletionLifecycleEventCommand,
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _LIFECYCLE_EVENT_INSERT_SQL,
                _lifecycle_event_values(command),
            )
            return int(cursor.lastrowid)

    def persist_client_finance_impact(
        self,
        command: ContractCompletionClientFinanceCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            persist_client_finance_terms_impact(cursor, command)

    def update_order_projection(
        self,
        command: ContractCompletionProjectionCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_UPDATE_SQL, _order_update_values(command))
            if cursor.rowcount != 1:
                raise RuntimeError("order_version_conflict")

    def append_outbox_intent(
        self,
        request: ContractCompletionApplyRequest,
        preview: ContractCompletionPreview,
        lifecycle_event_id: int,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                _outbox_values(request, preview, lifecycle_event_id),
            )

    def save_receipt(
        self,
        command: ContractCompletionReceiptCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_INSERT_SQL, _receipt_values(command))


def _load_facts(cursor, case_no, *, lock):
    order = _select_order(cursor, case_no, lock)
    completed = _select_contract_completion(cursor, case_no, lock)
    deposit_settled = _select_deposit_settlement(cursor, case_no, lock)
    client_finance = load_contract_client_finance_facts(
        cursor,
        order,
        lock=lock,
    )
    return ContractCompletionWorkflowFacts(
        _facts(order, completed, deposit_settled),
        client_finance,
        int(order["service_days"]),
    )


def _select_order(cursor, case_no, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_ORDER_SELECT_SQL + lock_clause, (case_no,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("order_not_found")
    return row


def _select_contract_completion(cursor, case_no, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_CONTRACT_EVENT_SELECT_SQL + lock_clause, (case_no,))
    return cursor.fetchone() is not None


def _select_deposit_settlement(cursor, case_no, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_DEPOSIT_SELECT_SQL + lock_clause, (case_no,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        return False
    return str(row["settlement_state"]) == "settled"


def _facts(order, contract_completed, deposit_settled):
    return ContractCompletionFacts(
        case_no=str(order["case_no"]),
        aggregate_version=int(order["lifecycle_version"]),
        contract_identity=_optional_text(order.get("contract_identity")),
        contract_completed=contract_completed,
        lifecycle_status=OrderLifecycleStatus(str(order["status"])),
        deposit_settled=deposit_settled,
        service_time=ServiceTimeTerms(
            _mysql_time(order.get("service_start_time")),
            _mysql_time(order.get("service_end_time")),
            order.get("service_end_day_offset"),
        ),
    )


def _insert_claim(cursor, request, command_fingerprint):
    try:
        cursor.execute(
            _CLAIM_INSERT_SQL,
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


def _locked_claim(cursor, key):
    cursor.execute(_CLAIM_SELECT_SQL, (key.value,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("idempotency_claim_missing")
    return row


def _claim_state(request, command_fingerprint, claim):
    expected = (_COMMAND_FAMILY, request.case_no, command_fingerprint.value)
    actual = (
        str(claim["command_family"]),
        str(claim["aggregate_identity"]),
        str(claim["command_fingerprint"]),
    )
    if actual == expected:
        return ContractCompletionCommandClaimState.MATCHED
    return ContractCompletionCommandClaimState.MISMATCH


def _contract_event_values(request, preview):
    return (
        request.case_no,
        preview.candidate.contract_identity,
        "contract_completed",
        request.actor.actor_id,
        request.reason,
        request.idempotency_key.value,
    )


def _lifecycle_event_values(command):
    candidate = command.candidate
    request = command.request
    return (
        candidate.case_no,
        "contract_completed",
        candidate.before_status.value,
        candidate.after_status.value,
        request.actor.actor_id,
        command.business_date,
        candidate.expected_order_version,
        request.idempotency_key.value,
        _canonical_json(_lifecycle_snapshot(candidate)),
    )


def _lifecycle_snapshot(candidate):
    return {
        "contract_completed": candidate.after_completed,
        "contract_identity": candidate.contract_identity,
        "deposit_settled": candidate.deposit_settled,
        "intent": candidate.intent.value,
        "preview_fingerprint": candidate.fingerprint.value,
        "resulting_order_version": candidate.resulting_order_version,
    }


def _order_update_values(command):
    return (
        command.lifecycle_status.value,
        command.resulting_order_version,
        command.case_no,
        command.expected_order_version,
    )


def _outbox_values(request, preview, lifecycle_event_id):
    candidate = preview.candidate
    intent_key = f"contract-completed:{request.idempotency_key.value}"
    payload = {
        "after_status": candidate.after_status.value,
        "before_status": candidate.before_status.value,
        "contract_event": "contract_completed",
        "preview_fingerprint": preview.fingerprint.value,
        "resulting_order_version": candidate.resulting_order_version,
    }
    return (
        candidate.case_no,
        lifecycle_event_id,
        intent_key,
        "lifecycle_projection_changed",
        _canonical_json(payload),
    )


# Kept cohesive so indexed receipt columns and immutable snapshot cannot drift.
def _receipt_values(command):
    stored = command.stored_receipt
    receipt = stored.receipt
    return (
        command.request.idempotency_key.value,
        stored.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        receipt.case_no,
        command.contract_event_id,
        command.lifecycle_event_id,
        receipt.order_version,
        receipt.lifecycle_status.value,
        receipt.contract_identity,
        command.request.correlation_id.value,
        _canonical_json(_receipt_payload(receipt)),
    )


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = _receipt_from_payload(payload)
    _validate_receipt_columns(row, receipt)
    return StoredContractCompletionReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _receipt_from_payload(payload):
    _require_exact_receipt_keys(payload)
    return ContractCompletionReceipt(
        case_no=_required_text(payload, "case_no"),
        contract_identity=_required_text(payload, "contract_identity"),
        order_version=_required_integer(payload, "order_version"),
        client_finance_version=_required_integer(
            payload,
            "client_finance_version",
        ),
        established_obligation_count=_required_integer(
            payload,
            "established_obligation_count",
        ),
        lifecycle_status=_lifecycle_status(payload),
        contract_completed=_required_boolean(payload, "contract_completed"),
        preview_fingerprint=PreviewFingerprint(
            _required_text(payload, "preview_fingerprint")
        ),
    )


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "contract_completed": receipt.contract_completed,
        "contract_identity": receipt.contract_identity,
        "client_finance_version": receipt.client_finance_version,
        "established_obligation_count": (
            receipt.established_obligation_count
        ),
        "lifecycle_status": receipt.lifecycle_status.value,
        "order_version": receipt.order_version,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _validate_receipt_columns(row, receipt):
    expected = (
        receipt.case_no,
        receipt.order_version,
        receipt.lifecycle_status.value,
        receipt.contract_identity,
        receipt.preview_fingerprint.value,
    )
    actual = (
        str(row["case_no"]),
        int(row["order_version"]),
        str(row["lifecycle_status"]),
        str(row["contract_identity"]),
        str(row["preview_fingerprint"]),
    )
    if actual != expected:
        raise ValueError("contract_completion_receipt_integrity_violation")


def _require_exact_receipt_keys(payload):
    if set(payload) != _RECEIPT_PAYLOAD_KEYS:
        raise ValueError("contract_completion_receipt_integrity_violation")


def _required_text(payload, key):
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("contract_completion_receipt_integrity_violation")
    return value


def _required_integer(payload, key):
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("contract_completion_receipt_integrity_violation")
    return value


def _required_boolean(payload, key):
    value = payload[key]
    if not isinstance(value, bool):
        raise ValueError("contract_completion_receipt_integrity_violation")
    return value


def _lifecycle_status(payload):
    try:
        return OrderLifecycleStatus(
            _required_text(payload, "lifecycle_status")
        )
    except ValueError as error:
        raise ValueError(
            "contract_completion_receipt_integrity_violation"
        ) from error


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("contract completion receipt must be an object")
    return parsed


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _optional_text(value):
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _mysql_time(value):
    if value is None or isinstance(value, time):
        return value
    if not isinstance(value, timedelta):
        raise TypeError("unsupported MySQL TIME value")
    seconds = int(value.total_seconds())
    if seconds < 0 or seconds >= 86_400:
        raise ValueError("invalid MySQL TIME value")
    return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)


def _mysql_error_code(error):
    if error.args and isinstance(error.args[0], int):
        return error.args[0]
    return None


_ORDER_SELECT_SQL = (
    "SELECT case_no,contract_identity,lifecycle_version,status,"
    "service_days,service_hours_per_day,floor_fee,"
    "service_start_time,service_end_time,service_end_day_offset "
    "FROM orders WHERE case_no=%s"
)
_CONTRACT_EVENT_SELECT_SQL = (
    "SELECT id FROM order_contract_flow_events "
    "WHERE case_no=%s AND event_type='contract_completed'"
)
_DEPOSIT_SELECT_SQL = (
    "SELECT settlement_state FROM client_deposit_settlement_projection "
    "WHERE case_no=%s"
)
_CLAIM_INSERT_SQL = (
    "INSERT INTO application_command_claims "
    "(idempotency_key,command_family,aggregate_identity,"
    "command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)"
)
_CLAIM_SELECT_SQL = (
    "SELECT command_family,aggregate_identity,command_fingerprint "
    "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE"
)
_CONTRACT_EVENT_INSERT_SQL = (
    "INSERT INTO order_contract_flow_events "
    "(case_no,contract_identity,event_type,actor,reason,idempotency_key) "
    "VALUES (%s,%s,%s,%s,%s,%s)"
)
_LIFECYCLE_EVENT_INSERT_SQL = (
    "INSERT INTO order_lifecycle_state_events "
    "(case_no,trigger_event,before_status,after_status,actor,business_date,"
    "expected_version,idempotency_key,facts_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_ORDER_UPDATE_SQL = (
    "UPDATE orders SET status=%s,lifecycle_version=%s "
    "WHERE case_no=%s AND lifecycle_version=%s"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO orders_domain_outbox "
    "(case_no,lifecycle_event_id,intent_key,intent_type,payload_snapshot) "
    "VALUES (%s,%s,%s,%s,%s)"
)
_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,case_no,order_version,"
    "lifecycle_status,contract_identity,result_snapshot "
    "FROM order_contract_completion_apply_receipts "
    "WHERE idempotency_key=%s"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO order_contract_completion_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "contract_event_id,lifecycle_event_id,order_version,lifecycle_status,"
    "contract_identity,correlation_id,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_RECEIPT_PAYLOAD_KEYS = frozenset(
    {
        "case_no",
        "client_finance_version",
        "contract_completed",
        "contract_identity",
        "established_obligation_count",
        "lifecycle_status",
        "order_version",
        "preview_fingerprint",
    }
)


__all__ = ["MySqlOrderContractCompletionRepository"]

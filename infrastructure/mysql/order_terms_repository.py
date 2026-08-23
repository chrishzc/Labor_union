"""
File: order_terms_repository.py
Description: 實作 Orders Terms transaction 與 typed borrowed owner read adapter。
"""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from pymysql.err import IntegrityError

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.orders.terms_workflow import (
    ClientFinanceImpactPersistenceCommand,
    CommandClaimState,
    LifecycleImpactPersistenceCommand,
    OrderTermsApplyRequest,
    OrderTermsPersistenceCommand,
    OrderTermsPreview,
    OrderTermsReceipt,
    OrderTermsReceiptPersistenceCommand,
    PayrollImpactPersistenceCommand,
    SchedulingReplacementCommand,
    SchedulingReplacementResult,
    StoredTermsReceipt,
    TermsWorkflowFacts,
)

from .client_finance_terms_writer import persist_client_finance_terms_impact
from .order_terms_read_model import (
    load_order_facts,
    load_locked_facts,
    load_preview_facts,
    preflight_staff_ids,
)
from .order_lifecycle_impact_writer import persist_order_lifecycle_impact
from .scheduling_replacement_writer import persist_scheduling_replacement
from .payroll_terms_writer import persist_payroll_terms_impact


class MySqlOrderTermsRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_for_preview(self, case_no: str) -> TermsWorkflowFacts:
        with self._connection.cursor() as cursor:
            return load_preview_facts(cursor, case_no)

    def load_order_terms(
        self, case_no: str, *, for_update: bool = False
    ):
        """Expose the owner root as a typed borrowed read for M3 coordination."""

        with self._connection.cursor() as cursor:
            return load_order_facts(cursor, case_no, for_update=for_update)

    def preflight_impacted_staff_ids(self, case_no: str) -> tuple[int, ...]:
        with self._connection.cursor() as cursor:
            return preflight_staff_ids(cursor, case_no)

    def load_for_apply(
        self,
        case_no: str,
        preflight_staff_ids: tuple[int, ...],
    ) -> TermsWorkflowFacts:
        with self._connection.cursor() as cursor:
            return load_locked_facts(cursor, case_no, preflight_staff_ids)

    def claim_command(
        self,
        request: OrderTermsApplyRequest,
        command_fingerprint: PreviewFingerprint,
    ) -> CommandClaimState:
        with self._connection.cursor() as cursor:
            if _insert_command_claim(cursor, request, command_fingerprint):
                return CommandClaimState.CREATED
            claim_row = _lock_command_claim(cursor, request.idempotency_key)
        return _claim_state(request, command_fingerprint, claim_row)

    def find_receipt(
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

    def append_terms_event(
        self,
        request: OrderTermsApplyRequest,
        preview: OrderTermsPreview,
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO order_terms_change_events "
                "(case_no,expected_order_version,resulting_order_version,"
                "preview_fingerprint,idempotency_key,actor,reason,"
                "correlation_id,before_terms,after_terms) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                _terms_event_values(request, preview),
            )
            return int(cursor.lastrowid)

    def replace_scheduling_generation(
        self,
        command: SchedulingReplacementCommand,
    ) -> SchedulingReplacementResult:
        with self._connection.cursor() as cursor:
            return persist_scheduling_replacement(cursor, command)

    def update_order_terms(
        self,
        command: OrderTermsPersistenceCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_UPDATE_SQL, _order_update_values(command))
            if cursor.rowcount != 1:
                raise RuntimeError("order_version_conflict")

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

    def persist_lifecycle_impact(
        self,
        command: LifecycleImpactPersistenceCommand,
    ) -> int:
        with self._connection.cursor() as cursor:
            return persist_order_lifecycle_impact(cursor, command)

    def save_receipt(
        self,
        command: OrderTermsReceiptPersistenceCommand,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                _receipt_insert_values(command),
            )


def _insert_command_claim(cursor, request, command_fingerprint) -> bool:
    try:
        cursor.execute(
            "INSERT INTO application_command_claims "
            "(idempotency_key,command_family,aggregate_identity,"
            "command_fingerprint,correlation_id) "
            "VALUES (%s,'orders_terms',%s,%s,%s)",
            (
                request.idempotency_key.value,
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


def _lock_command_claim(cursor, key: IdempotencyKey):
    cursor.execute(
        "SELECT command_family,aggregate_identity,command_fingerprint "
        "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
        (key.value,),
    )
    claim_row = cursor.fetchone()
    if not isinstance(claim_row, Mapping):
        raise RuntimeError("idempotency_claim_missing")
    return claim_row


def _claim_state(request, command_fingerprint, claim_row) -> CommandClaimState:
    expected = (
        "orders_terms",
        request.case_no,
        command_fingerprint.value,
    )
    actual = (
        str(claim_row["command_family"]),
        str(claim_row["aggregate_identity"]),
        str(claim_row["command_fingerprint"]),
    )
    if actual == expected:
        return CommandClaimState.MATCHED
    return CommandClaimState.MISMATCH


def _terms_event_values(request, preview) -> tuple[object, ...]:
    return (
        request.case_no,
        preview.order_version,
        preview.order_version + 1,
        preview.fingerprint.value,
        request.idempotency_key.value,
        request.actor.actor_id,
        request.reason,
        request.correlation_id.value,
        _canonical_json(preview.before.canonical_payload()),
        _canonical_json(preview.after.canonical_payload()),
    )


def _order_update_values(command) -> tuple[object, ...]:
    terms = command.terms
    return (
        terms.planned_start_date,
        command.planned_end_date,
        terms.service_days,
        terms.service_hours_per_day,
        terms.requires_cooking,
        terms.floor_fee.amount,
        terms.service_time.start_time,
        terms.service_time.end_time,
        terms.service_time.end_day_offset,
        command.actual_end_date,
        command.lifecycle_status.value,
        command.resulting_order_version,
        command.case_no,
        command.expected_order_version,
    )


def _receipt_insert_values(command) -> tuple[object, ...]:
    stored_receipt = command.stored_receipt
    receipt = stored_receipt.receipt
    return (
        command.key.value,
        stored_receipt.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        receipt.case_no,
        command.terms_event_id,
        command.scheduling_receipt_id,
        command.lifecycle_event_id,
        receipt.order_version,
        receipt.scheduling_version,
        receipt.scheduling_generation,
        receipt.client_finance_version,
        receipt.payroll_version,
        receipt.lifecycle_status.value,
        int(receipt.service_data_lock_formed),
        command.correlation_id.value,
        _canonical_json(_receipt_payload(receipt)),
    )


def _stored_receipt(row: Mapping[str, Any]) -> StoredTermsReceipt:
    payload = _json_object(row["result_snapshot"])
    _require_exact_receipt_keys(payload)
    receipt = OrderTermsReceipt(
        case_no=_required_text(payload, "case_no"),
        order_version=_required_integer(payload, "order_version"),
        scheduling_version=_required_integer(payload, "scheduling_version"),
        scheduling_generation=_required_integer(
            payload,
            "scheduling_generation",
        ),
        client_finance_version=_required_integer(
            payload,
            "client_finance_version",
        ),
        payroll_version=_required_integer(payload, "payroll_version"),
        lifecycle_status=_lifecycle_status(payload),
        service_data_lock_formed=_required_boolean(
            payload,
            "service_data_lock_formed",
        ),
        cancelled_assignment_ids=_integer_tuple(
            payload,
            "cancelled_assignment_ids",
        ),
        created_assignment_keys=_text_tuple(
            payload,
            "created_assignment_keys",
        ),
        official_service_day_count=_required_integer(
            payload,
            "official_service_day_count",
        ),
        official_service_hours=_required_integer(
            payload,
            "official_service_hours",
        ),
        preview_fingerprint=PreviewFingerprint(
            _required_text(payload, "preview_fingerprint")
        ),
    )
    _validate_receipt_columns(row, receipt)
    return StoredTermsReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _receipt_payload(receipt: OrderTermsReceipt) -> dict[str, object]:
    return {
        "cancelled_assignment_ids": receipt.cancelled_assignment_ids,
        "case_no": receipt.case_no,
        "client_finance_version": receipt.client_finance_version,
        "created_assignment_keys": receipt.created_assignment_keys,
        "official_service_day_count": receipt.official_service_day_count,
        "official_service_hours": receipt.official_service_hours,
        "lifecycle_status": receipt.lifecycle_status.value,
        "order_version": receipt.order_version,
        "payroll_version": receipt.payroll_version,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "scheduling_generation": receipt.scheduling_generation,
        "scheduling_version": receipt.scheduling_version,
        "service_data_lock_formed": receipt.service_data_lock_formed,
    }


def _validate_receipt_columns(row, receipt) -> None:
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
        raise ValueError("order_terms_receipt_integrity_violation")


def _require_exact_receipt_keys(payload: Mapping[str, Any]) -> None:
    if set(payload) != _RECEIPT_PAYLOAD_KEYS:
        raise ValueError("order_terms_receipt_integrity_violation")


def _required_text(payload, key) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("order_terms_receipt_integrity_violation")
    return value


def _required_integer(payload, key) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("order_terms_receipt_integrity_violation")
    return value


def _required_boolean(payload, key) -> bool:
    value = payload[key]
    if not isinstance(value, bool):
        raise ValueError("order_terms_receipt_integrity_violation")
    return value


def _lifecycle_status(payload):
    from domains.orders.lifecycle import OrderLifecycleStatus

    try:
        return OrderLifecycleStatus(_required_text(payload, "lifecycle_status"))
    except ValueError as error:
        raise ValueError("order_terms_receipt_integrity_violation") from error


def _integer_tuple(payload, key) -> tuple[int, ...]:
    values = payload[key]
    if not isinstance(values, list):
        raise ValueError("order_terms_receipt_integrity_violation")
    result = tuple(values)
    if any(not isinstance(value, int) or value <= 0 for value in result):
        raise ValueError("order_terms_receipt_integrity_violation")
    return result


def _text_tuple(payload, key) -> tuple[str, ...]:
    values = payload[key]
    if not isinstance(values, list):
        raise ValueError("order_terms_receipt_integrity_violation")
    result = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError("order_terms_receipt_integrity_violation")
    return result


def _json_object(value: Any) -> Mapping[str, Any]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("receipt snapshot must be an object")
    return parsed


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _mysql_error_code(error: IntegrityError) -> int | None:
    return error.args[0] if error.args and isinstance(error.args[0], int) else None


_ORDER_UPDATE_SQL = (
    "UPDATE orders SET start_date=%s,end_date=%s,service_days=%s,"
    "service_hours_per_day=%s,requires_cooking=%s,floor_fee=%s,service_start_time=%s,"
    "service_end_time=%s,service_end_day_offset=%s,actual_end_date=%s,"
    "status=%s,lifecycle_version=%s "
    "WHERE case_no=%s AND lifecycle_version=%s"
)

_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,case_no,order_version,"
    "scheduling_version,scheduling_generation,client_finance_version,"
    "payroll_version,lifecycle_status,service_data_lock_formed,"
    "result_snapshot "
    "FROM order_terms_apply_receipts WHERE idempotency_key=%s"
)

_RECEIPT_INSERT_SQL = (
    "INSERT INTO order_terms_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "order_terms_event_id,scheduling_command_receipt_id,lifecycle_event_id,"
    "order_version,"
    "scheduling_version,scheduling_generation,client_finance_version,"
    "payroll_version,lifecycle_status,service_data_lock_formed,"
    "correlation_id,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
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

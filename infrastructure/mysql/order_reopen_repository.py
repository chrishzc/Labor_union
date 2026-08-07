"""MySQL persistence adapter for controlled order reopening."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from pymysql.err import IntegrityError

from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.reopen import (
    ReopenFinancialEventFact,
    ReopenFinancialEventKind,
    ReopenOrderFacts,
)
from subsystems.orders.order_lifecycle_command_envelope import (
    lock_order_lifecycle_command_envelope,
)
from subsystems.orders.order_lifecycle_control_commands import (
    CancellationControlCommand,
    apply_order_lifecycle_control_command,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.orders.reopen_workflow import (
    OrderReopenApplyRequest,
    OrderReopenPreview,
    OrderReopenReceipt,
    ReopenOrderPersistenceCommand,
    ReopenReceiptPersistenceCommand,
    ReopenWorkflowFacts,
    StoredReopenReceipt,
)
from subsystems.orders.terms_workflow import CommandClaimState

_COMMAND_FAMILY = "orders_reopen"


class MySqlOrderReopenRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_for_preview(self, case_no):
        with self._connection.cursor() as cursor:
            return _load_facts(cursor, case_no, lock=False)

    def load_for_apply(self, case_no):
        with self._connection.cursor() as cursor:
            return _load_facts(cursor, case_no, lock=True)

    def find_receipt(self, key, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL + suffix, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def claim_command(self, request, command_fingerprint):
        with self._connection.cursor() as cursor:
            if _insert_claim(cursor, request, command_fingerprint):
                return CommandClaimState.CREATED
            row = _lock_claim(cursor, request.idempotency_key.value)
        return _claim_state(request, command_fingerprint, row)

    def append_reopen_event(self, request, preview):
        with self._connection.cursor() as cursor:
            cursor.execute(_EVENT_INSERT_SQL, _event_values(request, preview))
            return int(cursor.lastrowid)

    def clear_cancellation_control(self, request, reopen_event_id):
        with self._connection.cursor() as cursor:
            _require_reopen_event(cursor, request, reopen_event_id)
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
                    "clear",
                    request.actor.actor_id,
                    request.reason,
                    request.expected_order_version.value,
                    request.idempotency_key.value,
                ),
            )
        return result.event_id

    def append_reopen_lifecycle(
        self,
        request,
        preview,
        cancellation_control_event_id,
        business_date,
    ):
        with self._connection.cursor() as cursor:
            _require_cleared_control(
                cursor,
                request,
                cancellation_control_event_id,
            )
            event_id = _insert_lifecycle_event(
                cursor,
                request,
                preview,
                business_date,
            )
            _append_lifecycle_outbox(cursor, request, preview, event_id)
            return event_id

    def update_reopened_order(self, command):
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_UPDATE_SQL, _order_values(command))
            if cursor.rowcount != 1:
                raise RuntimeError("order_version_conflict")

    def save_receipt(self, command):
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_INSERT_SQL, _receipt_values(command))
            if cursor.rowcount != 1:
                raise RuntimeError("order_reopen_receipt_not_saved")


def _load_facts(cursor, case_no, *, lock):
    order = _load_order_row(cursor, case_no, lock)
    cancellation = _load_active_cancellation(cursor, case_no, lock)
    versions = _load_account_versions(cursor, case_no, lock)
    reconfirmed = _actual_start_reconfirmed(cursor, order, lock)
    financial_events = _load_financial_events(
        cursor,
        case_no,
        cancellation,
        lock,
    )
    order_facts = _order_facts(order, cancellation, reconfirmed)
    return ReopenWorkflowFacts(
        order_facts,
        financial_events,
        int(versions["client_finance_version"]),
        int(versions["payroll_version"]),
    )


def _load_order_row(cursor, case_no, lock):
    cursor.execute(_ORDER_SELECT_SQL + _lock_clause(lock), (case_no,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("order_not_found")
    return row


def _load_active_cancellation(cursor, case_no, lock):
    cursor.execute(
        _ACTIVE_CANCELLATION_SELECT_SQL + _lock_clause(lock),
        (case_no,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("order_reopen_requires_cancelled_order")
    return row


def _load_account_versions(cursor, case_no, lock):
    cursor.execute(_ACCOUNT_VERSION_SELECT_SQL + _lock_clause(lock), (case_no,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("order_reopen_finance_roots_missing")
    return row


def _actual_start_reconfirmed(cursor, order, lock):
    actual_start_date = order["actual_start_date"]
    if actual_start_date is None:
        return False
    cursor.execute(_RECONFIRM_SELECT_SQL + _lock_clause(lock), (order["case_no"],))
    row = cursor.fetchone()
    if row is None:
        return True
    return (
        str(row["state"]) == "cleared"
        and row["confirmed_start_date"] == actual_start_date
    )


def _order_facts(order, cancellation, reconfirmed):
    return ReopenOrderFacts(
        str(order["case_no"]),
        int(order["lifecycle_version"]),
        OrderLifecycleStatus(str(order["status"])),
        int(cancellation["cancellation_event_id"]),
        str(cancellation["cancellation_state"]) == "active",
        bool(order["contract_completed"]),
        bool(order["deposit_settled"]),
        order["actual_start_date"],
        int(cancellation["official_service_day_count"]) > 0,
        reconfirmed,
        bool(order["service_data_locked"]),
    )


def _load_financial_events(cursor, case_no, cancellation, lock):
    if lock:
        _lock_financial_lineage(cursor, case_no, cancellation)
    client_rows = _client_financial_rows(
        cursor,
        case_no,
        cancellation,
        lock,
    )
    staff_rows = _staff_financial_rows(
        cursor,
        case_no,
        cancellation,
        lock,
    )
    return _financial_event_facts((*client_rows, *staff_rows))


def _lock_financial_lineage(cursor, case_no, cancellation):
    client_identities = _client_obligation_identities(
        cursor,
        case_no,
        cancellation,
    )
    staff_identities = _staff_obligation_identities(
        cursor,
        case_no,
        cancellation,
    )
    _lock_identity_rows(cursor, "client_obligations", client_identities)
    _lock_identity_rows(cursor, "staff_obligations", staff_identities)
    _lock_identity_rows(
        cursor,
        "staff_payable_projections",
        staff_identities,
    )


def _client_obligation_identities(cursor, case_no, cancellation):
    cursor.execute(
        "SELECT obligation_identity FROM client_obligation_events "
        "WHERE case_no=%s AND source_event_identity "
        "LIKE CONCAT('order-cancellation:',%s,':client-finance:%%') "
        "ORDER BY obligation_identity FOR UPDATE",
        (case_no, int(cancellation["cancellation_event_id"])),
    )
    return _identity_tuple(cursor.fetchall())


def _staff_obligation_identities(cursor, case_no, cancellation):
    cursor.execute(
        "SELECT obligation_identity FROM staff_obligation_events "
        "WHERE case_no=%s AND resulting_payroll_version=%s "
        "ORDER BY obligation_identity FOR UPDATE",
        (case_no, int(cancellation["payroll_version"])),
    )
    return _identity_tuple(cursor.fetchall())


def _identity_tuple(rows):
    return tuple(sorted({str(row["obligation_identity"]) for row in rows}))


def _lock_identity_rows(cursor, table_name, identities):
    if not identities:
        return
    placeholders = ",".join("%s" for _ in identities)
    cursor.execute(
        f"SELECT obligation_identity FROM {table_name} "
        f"WHERE obligation_identity IN ({placeholders}) "
        "ORDER BY obligation_identity FOR UPDATE",
        identities,
    )
    cursor.fetchall()


def _client_financial_rows(cursor, case_no, cancellation, lock):
    cursor.execute(
        _CLIENT_FINANCIAL_EVENT_SQL + _lock_clause(lock),
        (
            case_no,
            int(cancellation["cancellation_event_id"]),
            cancellation["cancellation_created_at"],
        ),
    )
    return tuple(cursor.fetchall())


def _staff_financial_rows(cursor, case_no, cancellation, lock):
    cursor.execute(
        _STAFF_FINANCIAL_EVENT_SQL + _lock_clause(lock),
        (
            case_no,
            int(cancellation["payroll_version"]),
            cancellation["cancellation_created_at"],
        ),
    )
    return tuple(cursor.fetchall())


def _financial_event_facts(rows):
    facts: dict[str, ReopenFinancialEventFact] = {}
    for row in rows:
        identity = str(row["identity"])
        fact = ReopenFinancialEventFact(
            identity,
            ReopenFinancialEventKind(str(row["event_kind"])),
        )
        existing = facts.get(identity)
        if existing is not None and existing != fact:
            raise ValueError("order_reopen_financial_lineage_inconsistent")
        facts[identity] = fact
    return tuple(facts[key] for key in sorted(facts))


def _insert_claim(cursor, request, command_fingerprint):
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


def _lock_claim(cursor, idempotency_key):
    cursor.execute(
        "SELECT command_family,aggregate_identity,command_fingerprint "
        "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
        (idempotency_key,),
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


def _event_values(request, preview):
    candidate = preview.candidate
    return (
        candidate.case_no,
        candidate.cancellation_event_id,
        candidate.before_status.value,
        candidate.after_status.value,
        candidate.expected_order_version,
        candidate.expected_order_version + 1,
        preview.fingerprint.value,
        request.idempotency_key.value,
        request.actor.actor_id,
        request.reason,
        request.correlation_id.value,
    )


def _require_reopen_event(cursor, request, reopen_event_id):
    cursor.execute(
        "SELECT id FROM order_reopen_events "
        "WHERE id=%s AND case_no=%s AND idempotency_key=%s FOR UPDATE",
        (
            reopen_event_id,
            request.case_no,
            request.idempotency_key.value,
        ),
    )
    if cursor.fetchone() is None:
        raise RuntimeError("order_reopen_event_not_found")


def _require_cleared_control(cursor, request, control_event_id):
    cursor.execute(
        "SELECT id FROM order_lifecycle_control_events "
        "WHERE id=%s AND case_no=%s AND control_type='cancellation' "
        "AND action='clear' AND idempotency_key=%s FOR UPDATE",
        (
            control_event_id,
            request.case_no,
            request.idempotency_key.value,
        ),
    )
    if cursor.fetchone() is None:
        raise RuntimeError("order_reopen_control_event_not_found")


def _insert_lifecycle_event(cursor, request, preview, business_date):
    candidate = preview.candidate
    cursor.execute(
        _LIFECYCLE_EVENT_INSERT_SQL,
        (
            request.case_no,
            "order_reopen_applied",
            candidate.before_status.value,
            candidate.after_status.value,
            request.actor.actor_id,
            business_date,
            candidate.expected_order_version,
            request.idempotency_key.value,
            _canonical_json(_lifecycle_facts(request, preview)),
        ),
    )
    return int(cursor.lastrowid)


def _lifecycle_facts(request, preview):
    candidate = preview.candidate
    return {
        "cancellation_event_id": candidate.cancellation_event_id,
        "fresh_scheduling_preview_required": True,
        "reason": request.reason,
        "restored_assignment_ids": [],
        "restored_lock_ids": [],
        "restored_schedule_ids": [],
    }


def _append_lifecycle_outbox(cursor, request, preview, lifecycle_event_id):
    payload = {
        "after_status": preview.candidate.after_status.value,
        "correlation_id": request.correlation_id.value,
        "fresh_scheduling_preview_required": True,
        "resulting_order_version": (
            preview.candidate.expected_order_version + 1
        ),
    }
    cursor.execute(
        "INSERT INTO orders_domain_outbox "
        "(case_no,lifecycle_event_id,intent_key,intent_type,payload_snapshot) "
        "VALUES (%s,%s,%s,'lifecycle_projection_changed',%s)",
        (
            request.case_no,
            lifecycle_event_id,
            _child_identity(request, "orders-outbox"),
            _canonical_json(payload),
        ),
    )


def _child_identity(request, purpose):
    return "child:" + fingerprint_payload(
        {
            "domain": "orders",
            "outer_key": request.idempotency_key.value,
            "purpose": purpose,
        }
    ).value


def _order_values(command: ReopenOrderPersistenceCommand):
    return (
        command.lifecycle_status.value,
        command.resulting_order_version,
        command.case_no,
        command.expected_order_version,
    )


def _receipt_values(command: ReopenReceiptPersistenceCommand):
    receipt = command.stored_receipt.receipt
    return (
        command.key.value,
        command.stored_receipt.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        receipt.case_no,
        command.reopen_event_id,
        command.cancellation_control_event_id,
        command.lifecycle_event_id,
        receipt.cancellation_event_id,
        receipt.order_version,
        receipt.lifecycle_status.value,
        receipt.requires_fresh_scheduling_preview,
        command.correlation_id.value,
        _canonical_json(_receipt_payload(receipt)),
    )


def _receipt_payload(receipt):
    return {
        "cancellation_event_id": receipt.cancellation_event_id,
        "case_no": receipt.case_no,
        "lifecycle_status": receipt.lifecycle_status.value,
        "order_version": receipt.order_version,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "requires_fresh_scheduling_preview": (
            receipt.requires_fresh_scheduling_preview
        ),
    }


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    if set(payload) != _RECEIPT_PAYLOAD_KEYS:
        raise ValueError("order_reopen_receipt_integrity_violation")
    receipt = OrderReopenReceipt(
        _text(payload, "case_no"),
        _nonnegative_integer(payload, "order_version"),
        OrderLifecycleStatus(_text(payload, "lifecycle_status")),
        _positive_integer(payload, "cancellation_event_id"),
        _required_true(payload, "requires_fresh_scheduling_preview"),
        PreviewFingerprint(_text(payload, "preview_fingerprint")),
    )
    _validate_receipt_columns(row, receipt)
    return StoredReopenReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _validate_receipt_columns(row, receipt):
    expected = (
        receipt.case_no,
        receipt.order_version,
        receipt.lifecycle_status.value,
        receipt.cancellation_event_id,
        int(receipt.requires_fresh_scheduling_preview),
        receipt.preview_fingerprint.value,
    )
    actual = (
        str(row["case_no"]),
        int(row["order_version"]),
        str(row["lifecycle_status"]),
        int(row["cancellation_event_id"]),
        int(row["requires_fresh_scheduling_preview"]),
        str(row["preview_fingerprint"]),
    )
    if actual != expected:
        raise ValueError("order_reopen_receipt_integrity_violation")


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("order_reopen_receipt_integrity_violation")
    return parsed


def _text(payload, key):
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("order_reopen_receipt_integrity_violation")
    return value


def _nonnegative_integer(payload, key):
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("order_reopen_receipt_integrity_violation")
    return value


def _positive_integer(payload, key):
    value = _nonnegative_integer(payload, key)
    if value == 0:
        raise ValueError("order_reopen_receipt_integrity_violation")
    return value


def _required_true(payload, key):
    if payload[key] is not True:
        raise ValueError("order_reopen_receipt_integrity_violation")
    return True


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _lock_clause(lock):
    return " FOR UPDATE" if lock else ""


def _mysql_error_code(error):
    return error.args[0] if error.args and isinstance(error.args[0], int) else None


_ORDER_SELECT_SQL = (
    "SELECT o.case_no,o.status,o.lifecycle_version,o.actual_start_date,"
    "EXISTS(SELECT 1 FROM order_contract_flow_events contract_event "
    "WHERE contract_event.case_no=o.case_no "
    "AND contract_event.event_type='contract_completed') AS contract_completed,"
    "EXISTS(SELECT 1 FROM order_service_data_locks service_lock "
    "WHERE service_lock.case_no=o.case_no) AS service_data_locked,"
    "EXISTS(SELECT 1 FROM client_deposit_settlement_projection deposit "
    "WHERE deposit.case_no=o.case_no "
    "AND deposit.settlement_state='settled') AS deposit_settled "
    "FROM orders o WHERE o.case_no=%s"
)

_ACTIVE_CANCELLATION_SELECT_SQL = (
    "SELECT state.state AS cancellation_state,"
    "receipt.cancellation_event_id,receipt.payroll_version,"
    "event.official_service_day_count,"
    "event.created_at AS cancellation_created_at "
    "FROM order_lifecycle_control_state state "
    "JOIN order_cancellation_apply_receipts receipt "
    "ON receipt.cancellation_control_event_id=state.current_event_id "
    "AND receipt.case_no=state.case_no "
    "JOIN order_cancellation_events event "
    "ON event.id=receipt.cancellation_event_id "
    "AND event.case_no=receipt.case_no "
    "WHERE state.case_no=%s AND state.control_type='cancellation' "
    "AND state.control_key='order_cancelled' AND state.state='active'"
)

_ACCOUNT_VERSION_SELECT_SQL = (
    "SELECT client.aggregate_version AS client_finance_version,"
    "payroll.aggregate_version AS payroll_version "
    "FROM client_finance_accounts client "
    "JOIN payroll_case_accounts payroll ON payroll.case_no=client.case_no "
    "WHERE client.case_no=%s"
)

_RECONFIRM_SELECT_SQL = (
    "SELECT state,confirmed_start_date "
    "FROM order_lifecycle_control_state "
    "WHERE case_no=%s AND control_type='actual_start_reconfirmation' "
    "AND control_key='actual_start_reconfirmation'"
)

_CLIENT_FINANCIAL_EVENT_SQL = (
    "SELECT CONCAT('client-ledger:',ledger.id) AS identity,"
    "CASE ledger.entry_type "
    "WHEN 'refund' THEN 'client_refund' "
    "WHEN 'reversal' THEN 'client_reversal' "
    "ELSE 'client_settlement' END AS event_kind "
    "FROM client_obligation_events obligation_event "
    "JOIN client_ledger_obligation_allocations allocation "
    "ON allocation.obligation_identity=obligation_event.obligation_identity "
    "JOIN client_ledger_entries ledger "
    "ON ledger.id=allocation.ledger_entry_id "
    "WHERE obligation_event.case_no=%s "
    "AND obligation_event.source_event_identity "
    "LIKE CONCAT('order-cancellation:',%s,':client-finance:%%') "
    "AND ledger.created_at >= %s ORDER BY ledger.id"
)

_STAFF_FINANCIAL_EVENT_SQL = (
    "SELECT CONCAT('staff-payout:',payout.id) AS identity,"
    "CASE payout.event_type "
    "WHEN 'payout' THEN 'staff_payout' "
    "WHEN 'return' THEN 'staff_return' "
    "ELSE 'staff_reversal' END AS event_kind "
    "FROM staff_obligation_events obligation_event "
    "JOIN staff_payout_obligation_links payout_link "
    "ON payout_link.obligation_identity=obligation_event.obligation_identity "
    "JOIN staff_payout_events payout ON payout.id=payout_link.payout_event_id "
    "WHERE obligation_event.case_no=%s "
    "AND obligation_event.resulting_payroll_version=%s "
    "AND payout.created_at >= %s ORDER BY payout.id"
)

_EVENT_INSERT_SQL = (
    "INSERT INTO order_reopen_events "
    "(case_no,cancellation_event_id,before_status,after_status,"
    "expected_order_version,resulting_order_version,preview_fingerprint,"
    "idempotency_key,actor,reason,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
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

_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,case_no,"
    "cancellation_event_id,order_version,lifecycle_status,"
    "requires_fresh_scheduling_preview,result_snapshot "
    "FROM order_reopen_apply_receipts WHERE idempotency_key=%s"
)

_RECEIPT_INSERT_SQL = (
    "INSERT INTO order_reopen_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "reopen_event_id,cancellation_control_event_id,lifecycle_event_id,"
    "cancellation_event_id,order_version,lifecycle_status,"
    "requires_fresh_scheduling_preview,correlation_id,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_RECEIPT_PAYLOAD_KEYS = {
    "cancellation_event_id",
    "case_no",
    "lifecycle_status",
    "order_version",
    "preview_fingerprint",
    "requires_fresh_scheduling_preview",
}


__all__ = ["MySqlOrderReopenRepository"]

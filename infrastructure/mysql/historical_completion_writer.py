"""MySQL adapter for the historical accounting-completed lifecycle command."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pymysql.err import IntegrityError

from infrastructure.mysql.historical_client_finance_completion_read_adapter import (
    MySqlClientFinanceCompletionReadAdapter,
)
from infrastructure.mysql.historical_orders_scheduling_completion_read_adapter import (
    MySqlHistoricalOrdersSchedulingCompletionReadAdapter,
)
from infrastructure.mysql.historical_staff_payables_completion_read_adapter import (
    MySqlStaffPayablesCompletionReadAdapter,
)
from infrastructure.mysql.order_lifecycle_impact_writer import (
    persist_order_lifecycle_impact,
    persist_order_lifecycle_projection,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from subsystems.orders.historical_completion_apply import (
    ApplyHistoricalCompletion,
    HistoricalCompletionApplyFacts,
    HistoricalCompletionCandidate,
    HistoricalCompletionClaimState,
    HistoricalCompletionReceipt,
    StoredHistoricalCompletionReceipt,
    lifecycle_impact_candidate,
)
from subsystems.orders.historical_completion_oracle import (
    HistoricalCompletionFacts,
    evaluate_historical_completion,
)
from subsystems.orders.terms_workflow import LifecycleImpactPersistenceCommand


_COMMAND_FAMILY = "historical_accounting_completion"


class MySqlHistoricalCompletionWriter:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load(self, case_no: str, *, for_update: bool) -> HistoricalCompletionApplyFacts:
        actual_end_date = self._load_order_end(case_no, for_update=for_update)
        if for_update:
            self._lock_owner_roots(case_no)
        orders = MySqlHistoricalOrdersSchedulingCompletionReadAdapter(
            self._connection
        ).load_completion_readback(case_no)
        client = MySqlClientFinanceCompletionReadAdapter(
            self._connection
        ).load_completion_readback(case_no)
        staff = MySqlStaffPayablesCompletionReadAdapter(
            self._connection
        ).load_completion_readback(case_no)
        if orders is None or client is None or staff is None:
            raise ValueError("historical_accounting_completion_owner_root_missing")
        return HistoricalCompletionApplyFacts(
            evaluate_historical_completion(
                HistoricalCompletionFacts(case_no, orders, client, staff)
            ),
            actual_end_date,
        )

    def claim(self, request, command_fingerprint):
        with self._connection.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO application_command_claims "
                    "(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (
                        request.idempotency_key.value,
                        _COMMAND_FAMILY,
                        request.case_no,
                        command_fingerprint.value,
                        request.correlation_id.value,
                    ),
                )
                return HistoricalCompletionClaimState.CREATED
            except IntegrityError as error:
                if _mysql_error_code(error) != 1062:
                    raise
            cursor.execute(
                "SELECT command_family,aggregate_identity,command_fingerprint "
                "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
                (request.idempotency_key.value,),
            )
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise RuntimeError("idempotency_claim_missing")
        expected = (_COMMAND_FAMILY, request.case_no, command_fingerprint.value)
        actual = (
            str(row["command_family"]),
            str(row["aggregate_identity"]),
            str(row["command_fingerprint"]),
        )
        return (
            HistoricalCompletionClaimState.MATCHED
            if actual == expected
            else HistoricalCompletionClaimState.MISMATCH
        )

    def find_receipt(self, key: IdempotencyKey):
        event_key = _child_identity(key, "lifecycle-event")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.command_fingerprint,e.id,e.case_no,e.after_status,e.expected_version "
                "FROM application_command_claims c "
                "JOIN order_lifecycle_state_events e ON e.case_no=c.aggregate_identity "
                "AND e.idempotency_key=%s "
                "WHERE c.idempotency_key=%s AND c.command_family=%s FOR UPDATE",
                (event_key, key.value, _COMMAND_FAMILY),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        if not isinstance(row, Mapping):
            raise ValueError("historical_completion_receipt_invalid")
        return StoredHistoricalCompletionReceipt(
            PreviewFingerprint(str(row["command_fingerprint"])),
            HistoricalCompletionReceipt(
                str(row["case_no"]),
                int(row["id"]),
                int(row["expected_version"]) + 1,
                _completed_status(row["after_status"]),
            ),
        )

    def persist(self, request, candidate):
        command = LifecycleImpactPersistenceCommand(
            lifecycle_impact_candidate(candidate),
            candidate.expected_order_version,
            candidate.resulting_order_version,
            candidate.source_fingerprint,
            request.idempotency_key,
            request.actor,
            request.reason,
            request.correlation_id,
            "historical_accounting_settled",
        )
        with self._connection.cursor() as cursor:
            event_id = persist_order_lifecycle_impact(cursor, command)
            persist_order_lifecycle_projection(cursor, command)
        return HistoricalCompletionReceipt(
            candidate.case_no,
            event_id,
            candidate.resulting_order_version,
            candidate.after_status,
        )

    def _load_order_end(self, case_no: str, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT actual_end_date FROM orders WHERE case_no=%s" + suffix,
                (case_no,),
            )
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise ValueError("historical_order_not_found")
        return row.get("actual_end_date")

    def _lock_owner_roots(self, case_no: str) -> None:
        """Lock every case-scoped source consumed by the existing completion adapters."""

        statements = (
            ("SELECT id FROM order_lifecycle_state_events WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT id FROM historical_service_day_events WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT case_no FROM historical_service_day_projections WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT case_no FROM client_finance_accounts WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT obligation_identity FROM client_obligations WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT id FROM client_obligation_events WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT id FROM client_ledger_entries WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT ledger_entry_id FROM client_ledger_obligation_allocations WHERE obligation_identity IN (SELECT obligation_identity FROM client_obligations WHERE case_no=%s) FOR UPDATE", (case_no,)),
            ("SELECT case_no FROM payroll_case_accounts WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT id FROM staff_obligation_events WHERE case_no=%s FOR UPDATE", (case_no,)),
            ("SELECT staff_id FROM staff_payable_accounts WHERE staff_id IN (SELECT staff_id FROM staff_obligations WHERE case_no=%s) FOR UPDATE", (case_no,)),
            ("SELECT obligation_identity FROM staff_payable_projections WHERE obligation_identity IN (SELECT obligation_identity FROM staff_obligations WHERE case_no=%s) FOR UPDATE", (case_no,)),
            ("SELECT obligation_identity FROM historical_staff_payout_projections WHERE obligation_identity IN (SELECT obligation_identity FROM staff_obligations WHERE case_no=%s) FOR UPDATE", (case_no,)),
            ("SELECT event_id FROM historical_staff_payout_obligation_links WHERE obligation_identity IN (SELECT obligation_identity FROM staff_obligations WHERE case_no=%s) FOR UPDATE", (case_no,)),
            ("SELECT id FROM historical_staff_payout_events WHERE id IN (SELECT event_id FROM historical_staff_payout_obligation_links WHERE obligation_identity IN (SELECT obligation_identity FROM staff_obligations WHERE case_no=%s)) FOR UPDATE", (case_no,)),
            ("SELECT payout_event_id FROM staff_payout_obligation_links WHERE obligation_identity IN (SELECT obligation_identity FROM staff_obligations WHERE case_no=%s) FOR UPDATE", (case_no,)),
            ("SELECT id FROM staff_payout_events WHERE id IN (SELECT payout_event_id FROM staff_payout_obligation_links WHERE obligation_identity IN (SELECT obligation_identity FROM staff_obligations WHERE case_no=%s)) FOR UPDATE", (case_no,)),
            ("SELECT recovery_identity FROM staff_overpayment_recoveries WHERE staff_id IN (SELECT staff_id FROM staff_obligations WHERE case_no=%s) FOR UPDATE", (case_no,)),
            ("SELECT id FROM staff_overpayment_recovery_events WHERE recovery_identity IN (SELECT recovery_identity FROM staff_overpayment_recoveries WHERE staff_id IN (SELECT staff_id FROM staff_obligations WHERE case_no=%s)) FOR UPDATE", (case_no,)),
        )
        with self._connection.cursor() as cursor:
            for statement, parameters in statements:
                cursor.execute(statement, parameters)
                cursor.fetchall()


def _child_identity(key: IdempotencyKey, purpose: str) -> str:
    return "child:" + fingerprint_payload(
        {"outer_key": key.value, "domain": "orders", "purpose": purpose}
    ).value


def _completed_status(value: object):
    from domains.orders.lifecycle import OrderLifecycleStatus

    status = OrderLifecycleStatus(str(value))
    if status is not OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED:
        raise ValueError("historical_completion_receipt_invalid")
    return status


def _mysql_error_code(error: Exception) -> int | None:
    return error.args[0] if error.args and isinstance(error.args[0], int) else None


__all__ = ["MySqlHistoricalCompletionWriter"]

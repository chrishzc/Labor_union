"""Shared dispatch from classified finance-import rows to formal domain services."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import json
from typing import Any

from subsystems.client_finance.receipt_reconciliation import reconcile_client_receipt
from subsystems.finance_import.reconciliation_dispatch import maybe_alert_pending
from subsystems.government_subsidy.receipt_reconciliation import reconcile_government_subsidy
from subsystems.staff_payables.actual_transfer_reconciliation import reconcile_staff_actual_transfer


_BUSINESS_CLASSIFICATIONS = frozenset(
    {
        "client_receipt",
        "client_subsidy_return",
        "government_subsidy",
        "staff_salary",
        "staff_legacy_subsidy",
    }
)
_STAFF_COMPONENTS = (
    ("regular_salary", "service_salary"),
    ("floor_fee", "floor_fee_amount"),
    ("adjustment", "adjustment_amount"),
)


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _identity_ids(value: Any) -> list[int] | None:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return None
    if not isinstance(value, list):
        return None
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1
        for item in value
    ):
        return None
    return list(dict.fromkeys(value))


def _dispatch_row(cursor: Any, row_id: int) -> Mapping[str, Any]:
    cursor.execute(
        """SELECT id, classification_type, matched_identity_ids,
                  resolved_counterparty_account, classification_reason, debit
           FROM finance_import_rows
           WHERE id=%s
           FOR UPDATE""",
        (row_id,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("finance import row was not found")
    return row


def _staff_transfer_candidates(
    cursor: Any,
    dispatch_row: Mapping[str, Any],
) -> list[dict[str, Any]]:
    staff_ids = _identity_ids(dispatch_row.get("matched_identity_ids"))
    if staff_ids is None or len(staff_ids) != 1:
        return []
    try:
        debit = Decimal(str(dispatch_row.get("debit")))
    except (InvalidOperation, TypeError, ValueError):
        return []
    if not debit.is_finite() or debit <= 0:
        return []

    classification_type = dispatch_row.get("classification_type")
    payment_phase = (
        "second_subsidy"
        if classification_type == "staff_legacy_subsidy"
        else None
    )
    if payment_phase is None and classification_type != "staff_salary":
        return []

    cursor.execute(
        """SELECT id, staff_id
           FROM staff_monthly_settlements
           WHERE staff_id=%s AND status IN ('finalized','partially_paid')
           ORDER BY settlement_month, id
           FOR UPDATE""",
        (staff_ids[0],),
    )
    settlements = cursor.fetchall()
    plans: list[dict[str, Any]] = []
    for settlement in settlements:
        if not isinstance(settlement, Mapping):
            raise TypeError("cursor must return mapping settlement rows")
        settlement_id = _positive_id(settlement.get("id"), "settlement_id")
        cursor.execute(
            """SELECT id AS settlement_detail_id, service_salary,
                      legacy_subsidy_payable, floor_fee_amount,
                      adjustment_amount, legacy_subsidy_status, review_required
               FROM staff_monthly_settlement_details
               WHERE settlement_id=%s AND staff_id=%s
               ORDER BY id
               FOR UPDATE""",
            (settlement_id, staff_ids[0]),
        )
        details: dict[int, Mapping[str, Any]] = {}
        for detail in cursor.fetchall():
            if not isinstance(detail, Mapping):
                raise TypeError("cursor must return mapping settlement detail rows")
            detail_id = _positive_id(
                detail.get("settlement_detail_id"),
                "settlement_detail_id",
            )
            details[detail_id] = detail
        if not details:
            continue

        cursor.execute(
            """SELECT sta.settlement_detail_id, sta.component_type,
                      sta.allocated_amount, sat.transaction_type
               FROM staff_transfer_allocations sta
               JOIN staff_actual_transfers sat ON sat.id=sta.transfer_id
               WHERE sta.settlement_detail_id IN (
                   SELECT id FROM staff_monthly_settlement_details
                   WHERE settlement_id=%s
               )
                 AND sta.review_status='approved'
                 AND sat.transaction_status='succeeded'
               ORDER BY sta.id
               FOR UPDATE""",
            (settlement_id,),
        )
        paid: dict[tuple[int, str], Decimal] = {}
        for allocation in cursor.fetchall():
            if not isinstance(allocation, Mapping):
                raise TypeError("cursor must return mapping allocation rows")
            sign = (
                Decimal("-1")
                if allocation.get("transaction_type") == "reversal"
                else Decimal("1")
            )
            key = (
                _positive_id(
                    allocation.get("settlement_detail_id"),
                    "settlement_detail_id",
                ),
                str(allocation.get("component_type")),
            )
            paid[key] = paid.get(key, Decimal("0")) + sign * Decimal(
                str(allocation.get("allocated_amount") or 0)
            )

        phase = payment_phase
        if phase is None:
            has_legacy = any(
                Decimal(str(detail.get("legacy_subsidy_payable") or 0)) > 0
                for detail in details.values()
            )
            phase = "first_salary" if has_legacy else "normal"
        components = (
            (("legacy_subsidy", "legacy_subsidy_payable"),)
            if phase == "second_subsidy"
            else _STAFF_COMPONENTS
        )
        allocations: list[dict[str, Any]] = []
        valid = True
        for detail_id, detail in details.items():
            if phase == "second_subsidy" and (
                detail.get("legacy_subsidy_status") != "confirmed"
                or bool(detail.get("review_required"))
            ):
                valid = False
                break
            for component_type, column in components:
                amount = Decimal(str(detail.get(column) or 0))
                remaining = amount - paid.get(
                    (detail_id, component_type),
                    Decimal("0"),
                )
                if remaining < 0:
                    valid = False
                    break
                if remaining > 0:
                    allocations.append(
                        {
                            "settlement_detail_id": detail_id,
                            "component_type": component_type,
                            "allocated_amount": remaining,
                            "allocation_method": "explicit",
                        }
                    )
            if not valid:
                break
        allocated = sum(
            (item["allocated_amount"] for item in allocations),
            Decimal("0"),
        )
        if valid and allocations and allocated == debit:
            plans.append(
                {
                    "settlement_id": settlement_id,
                    "payment_phase": phase,
                    "allocations": allocations,
                }
            )
    return plans


def _formal_references(
    classification_type: str,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    references: dict[str, Any] = {}
    if classification_type == "client_receipt":
        transaction_ids = result.get("transaction_ids")
        if isinstance(transaction_ids, list):
            references["transaction_ids"] = transaction_ids[:3]
        references["client_payment_id"] = result.get("client_payment_id")
    elif classification_type == "client_subsidy_return":
        references["transaction_id"] = result.get("transaction_id")
    elif classification_type == "government_subsidy":
        references["batch_id"] = result.get("batch_id")
    elif classification_type in {"staff_salary", "staff_legacy_subsidy"}:
        references["transfer_id"] = result.get("transfer_id")
        settlement = result.get("settlement")
        if isinstance(settlement, Mapping):
            references["settlement_id"] = settlement.get("id")
    return {
        key: value
        for key, value in references.items()
        if value is not None
    }


def dispatch_finance_import_row(
    cursor: Any,
    finance_import_row_id: int,
    originating_batch_id: int,
) -> dict[str, Any]:
    """Dispatch one classified row without owning commit or rollback."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    row_id = _positive_id(finance_import_row_id, "finance_import_row_id")
    batch_id = _positive_id(originating_batch_id, "originating_batch_id")
    row = _dispatch_row(cursor, row_id)
    classification_type = row.get("classification_type")

    if classification_type == "non_business_review":
        domain_result: Mapping[str, Any] = {
            "result": "pending",
            "reason": row.get("classification_reason") or "non_business_review",
        }
    elif classification_type == "client_receipt":
        domain_result = reconcile_client_receipt(cursor, row_id)
    elif classification_type == "client_subsidy_return":
        # subsidy_return dispatch has no canonical implementation: the legacy
        # writer (services/client_subsidy_return_transactions.py) was removed
        # by the subsidy_advance redesign (see 架構重整/25) and must not be
        # reintroduced as a compatibility path. Fail closed until a typed
        # subsidy_advance dispatch replacement is authorized.
        raise NotImplementedError(
            "client_subsidy_return dispatch is unimplemented pending the "
            "subsidy_advance redesign; see document/架構重整/"
            "02_決策與退役執行記錄/25_Client_Refund_Completion_Decision_Package.md"
        )
    elif classification_type == "government_subsidy":
        domain_result = reconcile_government_subsidy(cursor, row_id)
    elif classification_type in {"staff_salary", "staff_legacy_subsidy"}:
        plans = _staff_transfer_candidates(cursor, row)
        if len(plans) != 1:
            domain_result = {
                "result": "pending",
                "reason": "staff_transfer_plan_not_unique",
            }
        else:
            plan = plans[0]
            domain_result = reconcile_staff_actual_transfer(
                cursor,
                row_id,
                plan["settlement_id"],
                plan["payment_phase"],
                plan["allocations"],
            )
    else:
        raise ValueError("finance import row has an unsupported classification")

    if not isinstance(domain_result, Mapping):
        raise TypeError("finance domain service must return a mapping")
    result_status = domain_result.get("result")
    if result_status not in {"reconciled", "existing", "pending"}:
        raise ValueError("finance domain service returned an unsupported result")
    finance_alert_action = None
    if result_status == "pending" and classification_type in _BUSINESS_CLASSIFICATIONS:
        alert_result = maybe_alert_pending(
            cursor,
            classification_type=str(classification_type),
            row_id=row_id,
            batch_id=batch_id,
            result=domain_result,
        )
        if isinstance(alert_result, Mapping):
            finance_alert_action = alert_result.get("result")
    return {
        "classification_type": classification_type,
        "result": result_status,
        "reason": domain_result.get("reason"),
        "formal_references": _formal_references(
            str(classification_type),
            domain_result,
        ),
        "finance_alert_action": finance_alert_action,
    }

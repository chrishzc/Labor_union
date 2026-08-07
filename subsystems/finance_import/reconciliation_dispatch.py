"""Dispatch a classified finance row while the diagnostic caller rolls back the UoW."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import json
from typing import Any

from subsystems.staff_payables.actual_transfer_reconciliation import (
    reconcile_staff_actual_transfer,
)
from subsystems.client_finance.receipt_reconciliation import (
    reconcile_client_receipt,
)
from subsystems.government_subsidy.receipt_reconciliation import (
    reconcile_government_subsidy,
)


_STAFF_COMPONENTS = (
    ("regular_salary", "service_salary"),
    ("floor_fee", "floor_fee_amount"),
    ("adjustment", "adjustment_amount"),
)


def maybe_alert_pending(*_args: Any, **_kwargs: Any) -> None:
    return None


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
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in value):
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


def _staff_transfer_candidates(cursor: Any, dispatch_row: Mapping[str, Any]) -> list[dict[str, Any]]:
    staff_ids = _identity_ids(dispatch_row.get("matched_identity_ids"))
    if staff_ids is None or len(staff_ids) != 1:
        return []
    try:
        debit = Decimal(str(dispatch_row.get("debit")))
        if not debit.is_finite() or debit <= 0:
            return []
        classification = dispatch_row.get("classification_type")
        phase = "second_subsidy" if classification == "staff_legacy_subsidy" else None
        if phase is None and classification != "staff_salary":
            return []
        cursor.execute(
            """SELECT id, staff_id
               FROM staff_monthly_settlements
               WHERE staff_id=%s AND status IN ('finalized','partially_paid')
               ORDER BY settlement_month, id
               FOR UPDATE""",
            (staff_ids[0],),
        )
        plans = []
        for settlement in cursor.fetchall():
            if not isinstance(settlement, Mapping):
                raise TypeError("cursor must return mapping settlement rows")
            settlement_id = _positive_id(settlement.get("id"), "settlement_id")
            details = _settlement_details(cursor, settlement_id, staff_ids[0])
            if not details:
                continue
            paid = _paid_allocations(cursor, settlement_id)
            resolved_phase = phase or _salary_phase(details)
            allocations = _remaining_allocations(details, paid, resolved_phase)
            if allocations and sum((item["allocated_amount"] for item in allocations), Decimal("0")) == debit:
                plans.append({"settlement_id": settlement_id, "payment_phase": resolved_phase, "allocations": allocations})
        return plans
    except (InvalidOperation, TypeError, ValueError):
        return []


def _settlement_details(cursor: Any, settlement_id: int, staff_id: int) -> dict[int, Mapping[str, Any]]:
    cursor.execute(
        """SELECT id AS settlement_detail_id, service_salary,
                  legacy_subsidy_payable, floor_fee_amount,
                  adjustment_amount, legacy_subsidy_status, review_required
           FROM staff_monthly_settlement_details
           WHERE settlement_id=%s AND staff_id=%s
           ORDER BY id
           FOR UPDATE""",
        (settlement_id, staff_id),
    )
    details = {}
    for detail in cursor.fetchall():
        if not isinstance(detail, Mapping):
            raise TypeError("cursor must return mapping settlement detail rows")
        details[_positive_id(detail.get("settlement_detail_id"), "settlement_detail_id")] = detail
    return details


def _paid_allocations(cursor: Any, settlement_id: int) -> dict[tuple[int, str], Decimal]:
    cursor.execute(
        """SELECT sta.settlement_detail_id, sta.component_type,
                  sta.allocated_amount, sat.transaction_type
           FROM staff_transfer_allocations sta
           JOIN staff_actual_transfers sat ON sat.id=sta.transfer_id
           WHERE sta.settlement_detail_id IN (
               SELECT id FROM staff_monthly_settlement_details
               WHERE settlement_id=%s
           ) AND sta.review_status='approved'
             AND sat.transaction_status='succeeded'
           ORDER BY sta.id
           FOR UPDATE""",
        (settlement_id,),
    )
    paid: dict[tuple[int, str], Decimal] = {}
    for allocation in cursor.fetchall():
        if not isinstance(allocation, Mapping):
            raise TypeError("cursor must return mapping allocation rows")
        sign = Decimal("-1") if allocation.get("transaction_type") == "reversal" else Decimal("1")
        key = (_positive_id(allocation.get("settlement_detail_id"), "settlement_detail_id"), str(allocation.get("component_type")))
        paid[key] = paid.get(key, Decimal("0")) + sign * Decimal(str(allocation.get("allocated_amount") or 0))
    return paid


def _salary_phase(details: Mapping[int, Mapping[str, Any]]) -> str:
    return "first_salary" if any(Decimal(str(row.get("legacy_subsidy_payable") or 0)) > 0 for row in details.values()) else "normal"


def _remaining_allocations(details: Mapping[int, Mapping[str, Any]], paid: Mapping[tuple[int, str], Decimal], phase: str) -> list[dict[str, Any]]:
    components = (("legacy_subsidy", "legacy_subsidy_payable"),) if phase == "second_subsidy" else _STAFF_COMPONENTS
    allocations = []
    for detail_id, detail in details.items():
        if phase == "second_subsidy" and (detail.get("legacy_subsidy_status") != "confirmed" or bool(detail.get("review_required"))):
            return []
        for component_type, column in components:
            remaining = Decimal(str(detail.get(column) or 0)) - paid.get((detail_id, component_type), Decimal("0"))
            if remaining < 0:
                return []
            if remaining > 0:
                allocations.append({"settlement_detail_id": detail_id, "component_type": component_type, "allocated_amount": remaining, "allocation_method": "explicit"})
    return allocations


def _formal_references(classification_type: str, result: Mapping[str, Any]) -> dict[str, Any]:
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
    return {key: value for key, value in references.items() if value is not None}


def dispatch_finance_import_row(cursor: Any, finance_import_row_id: int, originating_batch_id: int) -> dict[str, Any]:
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    row_id = _positive_id(finance_import_row_id, "finance_import_row_id")
    _positive_id(originating_batch_id, "originating_batch_id")
    row = _dispatch_row(cursor, row_id)
    classification = row.get("classification_type")
    if classification == "non_business_review":
        result: Mapping[str, Any] = {"result": "pending", "reason": row.get("classification_reason") or "non_business_review"}
    elif classification == "client_receipt":
        result = reconcile_client_receipt(cursor, row_id)
    elif classification == "client_subsidy_return":
        result = {
            "result": "pending",
            "reason": "legacy_client_subsidy_return_dispatch_retired",
        }
    elif classification == "government_subsidy":
        result = reconcile_government_subsidy(cursor, row_id)
    elif classification in {"staff_salary", "staff_legacy_subsidy"}:
        plans = _staff_transfer_candidates(cursor, row)
        result = {"result": "pending", "reason": "staff_transfer_plan_not_unique"} if len(plans) != 1 else reconcile_staff_actual_transfer(cursor, row_id, plans[0]["settlement_id"], plans[0]["payment_phase"], plans[0]["allocations"])
    else:
        raise ValueError("finance import row has an unsupported classification")
    if not isinstance(result, Mapping):
        raise TypeError("finance domain service must return a mapping")
    if result.get("result") not in {"pending", "reconciled", "existing"}:
        raise ValueError("finance domain service returned an unsupported result")
    return {"classification_type": classification, "result": result["result"], "reason": result.get("reason"), "formal_references": _formal_references(str(classification), result), "finance_alert_action": None}

"""Pure validation and calculation rules for the split payment ledgers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _money(value: Any, field: str, *, allow_negative: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not allow_negative and amount < 0:
        raise ValueError(f"{field} cannot be negative")
    return amount


def _output_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _invalid(message: str) -> dict[str, Any]:
    return {"valid": False, "error": message}


def _assignment_allocation(data: dict[str, Any]) -> dict[str, Any]:
    order_hours = _money(data.get("order_hours"), "order_hours")
    order_floor_fee = _money(data.get("floor_fee"), "floor_fee")
    assignments = data.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        return _invalid("at least one assignment is required")

    assigned_hours = Decimal("0")
    allocated_floor_fee = Decimal("0")
    for index, assignment in enumerate(assignments, start=1):
        if not isinstance(assignment, dict) or not assignment.get("staff_id"):
            return _invalid(f"assignment {index} has no staff_id")
        assigned_hours += _money(assignment.get("hours"), f"assignment {index} hours")
        allocated_floor_fee += _money(assignment.get("floor_fee"), f"assignment {index} floor_fee")

    if assigned_hours > order_hours:
        return _invalid("assigned hours exceed order hours")
    if allocated_floor_fee > order_floor_fee:
        return _invalid("allocated floor fee exceeds order floor fee")
    if data.get("finalized") and assigned_hours != order_hours:
        return _invalid("finalized assignments must equal order hours")
    if data.get("finalized") and allocated_floor_fee != order_floor_fee:
        return _invalid("finalized floor fee must equal order floor fee")
    return {
        "valid": True,
        "assigned_hours": _output_number(assigned_hours),
        "allocated_floor_fee": _output_number(allocated_floor_fee),
    }


def _staff_portfolio(data: dict[str, Any]) -> dict[str, Any]:
    if not data.get("staff_id"):
        return _invalid("staff_id is required")
    payments = data.get("payments")
    if not isinstance(payments, list):
        return _invalid("payments must be a list")
    pending_statuses = {"pending", "partially_paid", "review_required"}
    pending = [payment for payment in payments if payment.get("status") in pending_statuses]
    if any(not payment.get("case_no") for payment in pending):
        return _invalid("pending payment has no case_no")
    return {
        "valid": True,
        "pending_payment_count": len(pending),
        "case_count": len({payment["case_no"] for payment in pending}),
    }


def _transaction_net(data: dict[str, Any]) -> dict[str, Any]:
    positive_types = set(data.get("positive_types") or [])
    negative_types = set(data.get("negative_types") or [])
    if not positive_types or positive_types & negative_types:
        return _invalid("transaction type directions are invalid")
    transactions = data.get("transactions")
    if not isinstance(transactions, list):
        return _invalid("transactions must be a list")

    references: set[str] = set()
    net = Decimal("0")
    for index, transaction in enumerate(transactions, start=1):
        if not isinstance(transaction, dict):
            return _invalid(f"transaction {index} is invalid")
        reference = transaction.get("external_reference")
        if not isinstance(reference, str) or not reference.strip() or reference in references:
            return _invalid(f"transaction {index} has duplicate or empty external_reference")
        references.add(reference)
        amount = _money(transaction.get("amount"), f"transaction {index} amount")
        if amount == 0:
            return _invalid(f"transaction {index} amount must be positive")
        if transaction.get("transaction_status") != "succeeded":
            continue
        transaction_type = transaction.get("transaction_type")
        if transaction_type in positive_types:
            net += amount
        elif transaction_type in negative_types:
            net -= amount
        else:
            return _invalid(f"transaction {index} type has no direction")
    return {"valid": True, "net_amount": _output_number(net)}


def evaluate_payment_boundary(scenario: str, **payment_data: Any) -> dict[str, Any]:
    """Evaluate one payment edge-case without touching the database."""
    try:
        if scenario == "assignment_allocation":
            return _assignment_allocation(payment_data)
        if scenario == "staff_portfolio":
            return _staff_portfolio(payment_data)
        if scenario == "transaction_net":
            return _transaction_net(payment_data)
        return _invalid(f"unsupported scenario: {scenario}")
    except ValueError as exc:
        return _invalid(str(exc))

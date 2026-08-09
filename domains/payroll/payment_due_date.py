"""Canonical due-date policy for an assignment-owned staff payable."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation


def calculate_staff_payment_due_date(
    completed_on: date,
    client_payable_amount: Decimal | int,
    is_full_subsidy_order: bool,
) -> date:
    """Return the fifteenth selected from the derived funding state."""
    if not isinstance(completed_on, date):
        raise TypeError("completed_on must be a date")
    payable_amount = _nonnegative_decimal(client_payable_amount)
    if payable_amount > 0:
        months_after_completion = 1
    elif is_full_subsidy_order:
        months_after_completion = 2
    else:
        raise ValueError("zero client payable requires a full subsidy order")
    return _fifteenth_after_months(completed_on, months_after_completion)


def is_full_subsidy_eligible(client_identity_status: str) -> bool:
    if not isinstance(client_identity_status, str):
        raise TypeError("client_identity_status must be a string")
    normalized = client_identity_status.strip()
    if not normalized:
        raise ValueError("client_identity_status is required")
    return normalized == "補助市民"


def _nonnegative_decimal(value: Decimal | int) -> Decimal:
    if isinstance(value, bool):
        raise TypeError("client_payable_amount must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TypeError("client_payable_amount must be numeric") from exc
    if result < 0:
        raise ValueError("client_payable_amount cannot be negative")
    return result


def _fifteenth_after_months(value: date, month_count: int) -> date:
    month_index = value.month - 1 + month_count
    return date(value.year + month_index // 12, month_index % 12 + 1, 15)


__all__ = [
    "calculate_staff_payment_due_date",
    "is_full_subsidy_eligible",
]

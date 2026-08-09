"""Read-only monthly Payroll aggregation across a staff member's cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_positive_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191


class MonthlyPayrollDirection(StrEnum):
    PAYABLE_TO_STAFF = "payable_to_staff"
    RECEIVABLE_FROM_STAFF = "receivable_from_staff"


@dataclass(frozen=True, slots=True)
class MonthlyPayrollObligationFact:
    obligation_identity: str
    case_no: str
    assignment_id: int
    staff_id: int
    due_date: date
    direction: MonthlyPayrollDirection
    amount_due: MoneyNTD

    def __post_init__(self) -> None:
        require_canonical_text(
            self.obligation_identity,
            "obligation identity",
            _IDENTITY_MAXIMUM_LENGTH,
        )
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.assignment_id, "assignment id")
        require_positive_integer(self.staff_id, "staff id")
        if not isinstance(self.due_date, date):
            raise TypeError("due date must be date")
        if not isinstance(self.amount_due, MoneyNTD):
            raise TypeError("amount due must be MoneyNTD")
        require_positive_integer(self.amount_due.amount, "amount due")


@dataclass(frozen=True, slots=True)
class StaffMonthlyPayrollSummary:
    staff_id: int
    year: int
    month: int
    case_count: int
    obligation_count: int
    payable_total: MoneyNTD
    receivable_total: MoneyNTD
    net_payable: MoneyNTD
    obligations: tuple[MonthlyPayrollObligationFact, ...]


# Kept cohesive because payable, receivable, and net are one monthly invariant.
def build_staff_monthly_payroll_summary(
    staff_id: int,
    year: int,
    month: int,
    obligations: tuple[MonthlyPayrollObligationFact, ...],
) -> StaffMonthlyPayrollSummary:
    require_positive_integer(staff_id, "staff id")
    _validate_year_month(year, month)
    _validate_obligations(staff_id, year, month, obligations)
    payable_total = _sum_direction(
        obligations,
        MonthlyPayrollDirection.PAYABLE_TO_STAFF,
    )
    receivable_total = _sum_direction(
        obligations,
        MonthlyPayrollDirection.RECEIVABLE_FROM_STAFF,
    )
    return StaffMonthlyPayrollSummary(
        staff_id=staff_id,
        year=year,
        month=month,
        case_count=len({item.case_no for item in obligations}),
        obligation_count=len(obligations),
        payable_total=payable_total,
        receivable_total=receivable_total,
        net_payable=payable_total - receivable_total,
        obligations=obligations,
    )


def _validate_year_month(year: int, month: int) -> None:
    if isinstance(year, bool) or not isinstance(year, int):
        raise TypeError("year must be integer")
    if year < 2000 or year > 2200:
        raise ValueError("invalid_payroll_facts")
    if isinstance(month, bool) or not isinstance(month, int):
        raise TypeError("month must be integer")
    if month < 1 or month > 12:
        raise ValueError("invalid_payroll_facts")


def _validate_obligations(staff_id, year, month, obligations) -> None:
    if not isinstance(obligations, tuple):
        raise TypeError("monthly obligations must be a tuple")
    identities = tuple(item.obligation_identity for item in obligations)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("invalid_payroll_facts")
    for item in obligations:
        if item.staff_id != staff_id:
            raise ValueError("invalid_payroll_facts")
        if (item.due_date.year, item.due_date.month) != (year, month):
            raise ValueError("invalid_payroll_facts")


def _sum_direction(obligations, direction) -> MoneyNTD:
    return MoneyNTD(
        sum(
            item.amount_due.amount
            for item in obligations
            if item.direction is direction
        )
    )


__all__ = [
    "MonthlyPayrollDirection",
    "MonthlyPayrollObligationFact",
    "StaffMonthlyPayrollSummary",
    "build_staff_monthly_payroll_summary",
]

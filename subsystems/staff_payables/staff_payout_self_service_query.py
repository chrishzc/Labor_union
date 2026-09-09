"""Canonical read-only Staff Payables view for verified staff self-service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StaffPayoutTransactionView:
    transaction_type: str
    transaction_status: str
    amount: Decimal
    occurred_at: date


@dataclass(frozen=True, slots=True)
class StaffPayoutItemView:
    assignment_id: int
    case_no: str
    staff_id: int
    total_payable: Decimal
    amount_paid: Decimal
    due_date: date
    paid_at: date | None
    payment_status: str
    transactions: tuple[StaffPayoutTransactionView, ...] = ()


class StaffPayoutSelfServiceRepository(Protocol):
    def query_by_staff_and_payment_month(
        self, staff_id: int, year: int, month: int
    ) -> tuple[StaffPayoutItemView, ...]: ...


class StaffPayoutSelfServiceQuery:
    def __init__(self, repository: StaffPayoutSelfServiceRepository) -> None:
        self._repository = repository

    def query(self, staff_id: int, year: int, month: int) -> tuple[StaffPayoutItemView, ...]:
        if staff_id <= 0:
            raise ValueError("staff id must be positive")
        if year < 1900 or year > 2100:
            raise ValueError("payment year is out of range")
        if month < 1 or month > 12:
            raise ValueError("payment month is out of range")
        return self._repository.query_by_staff_and_payment_month(staff_id, year, month)


__all__ = [
    "StaffPayoutItemView",
    "StaffPayoutSelfServiceQuery",
    "StaffPayoutSelfServiceRepository",
    "StaffPayoutTransactionView",
]

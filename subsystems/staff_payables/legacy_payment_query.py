"""
Read-only query contract for the historical ``staff_payments`` projection.

The table is a compatibility projection, not the Staff Payables obligation
source of truth.  Keeping this contract in the Staff Payables subsystem lets
the legacy UI read a bounded, typed view while the canonical payable query is
used for new payout workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from shared_kernel.validation import require_canonical_text


@dataclass(frozen=True, slots=True)
class StaffPaymentTransactionView:
    id: int
    staff_payment_id: int
    case_no: str
    staff_id: int
    transaction_type: str
    transaction_status: str
    amount: Decimal
    occurred_at: date | None
    external_reference: str | None
    reversal_of_transaction_id: int | None
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class StaffPaymentSummaryView:
    id: int
    assignment_id: int
    case_no: str
    staff_id: int
    service_hours: Decimal
    hourly_rate: Decimal
    service_salary: Decimal
    floor_fee_amount: Decimal
    adjustment_amount: Decimal
    total_payable: Decimal
    amount_paid: Decimal
    due_date: date | None
    paid_at: date | None
    payment_status: str
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None
    transactions: tuple[StaffPaymentTransactionView, ...] = ()


class StaffPaymentQueryRepository(Protocol):
    def query_all(self) -> tuple[StaffPaymentSummaryView, ...]: ...

    def query_by_case_no(self, case_no: str) -> tuple[StaffPaymentSummaryView, ...]: ...


class StaffPaymentQueryApplication:
    """Application facade for the compatibility read model.

    It deliberately exposes no mutation or transaction methods.  The request
    dependency owns the borrowed connection lifecycle; this application only
    delegates a read to the typed repository port.
    """

    def __init__(self, repository: StaffPaymentQueryRepository) -> None:
        self._repository = repository

    def query_all(self) -> tuple[StaffPaymentSummaryView, ...]:
        return self._repository.query_all()

    def query_by_case_no(self, case_no: str) -> tuple[StaffPaymentSummaryView, ...]:
        return self._repository.query_by_case_no(
            require_canonical_text(case_no, "case number", 50)
        )


__all__ = [
    "StaffPaymentQueryApplication",
    "StaffPaymentQueryRepository",
    "StaffPaymentSummaryView",
    "StaffPaymentTransactionView",
]

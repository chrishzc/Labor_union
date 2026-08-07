"""State machine for funding a Staff Payables obligation without side effects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.money import MoneyNTD


class StaffPayoutFundingState(StrEnum):
    NOT_DUE = "not_due"
    CLIENT_RECEIPT_REQUIRED = "client_receipt_required"
    AWAITING_GOVERNMENT_RECEIPT = "awaiting_government_receipt"
    GOVERNMENT_FUNDED = "government_funded"
    UNION_ADVANCE_DUE = "union_advance_due"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True, slots=True)
class StaffPayoutFundingFacts:
    due_date: date
    staff_payable: MoneyNTD
    client_payable_amount: MoneyNTD
    is_full_subsidy_order: bool
    government_receipt_allocated: MoneyNTD
    union_advance_paid: MoneyNTD

    def __post_init__(self) -> None:
        if not isinstance(self.due_date, date):
            raise TypeError("due_date must be a date")
        for value in (
            self.staff_payable,
            self.client_payable_amount,
            self.government_receipt_allocated,
            self.union_advance_paid,
        ):
            if not isinstance(value, MoneyNTD):
                raise TypeError("funding amounts must be MoneyNTD")
        if self.staff_payable.amount <= 0:
            raise ValueError("staff_payable must be positive")
        if not isinstance(self.is_full_subsidy_order, bool):
            raise TypeError("is_full_subsidy_order must be bool")
        if self.client_payable_amount.amount == 0 and not self.is_full_subsidy_order:
            raise ValueError("zero client payable requires a full subsidy order")


def determine_staff_payout_funding_state(
    facts: StaffPayoutFundingFacts,
    business_date: date,
) -> StaffPayoutFundingState:
    """Choose one funding path; this function never creates a payout or offset."""
    if not isinstance(business_date, date):
        raise TypeError("business_date must be a date")
    if _has_inconsistent_funding(facts):
        return StaffPayoutFundingState.REVIEW_REQUIRED
    if business_date < facts.due_date:
        return StaffPayoutFundingState.NOT_DUE
    if facts.client_payable_amount.amount > 0:
        return StaffPayoutFundingState.CLIENT_RECEIPT_REQUIRED
    if facts.government_receipt_allocated.amount == facts.staff_payable.amount:
        return StaffPayoutFundingState.GOVERNMENT_FUNDED
    if facts.government_receipt_allocated.amount == 0:
        return StaffPayoutFundingState.UNION_ADVANCE_DUE
    return StaffPayoutFundingState.REVIEW_REQUIRED


def _has_inconsistent_funding(facts: StaffPayoutFundingFacts) -> bool:
    if facts.government_receipt_allocated.amount > facts.staff_payable.amount:
        return True
    return facts.union_advance_paid.amount > facts.staff_payable.amount


__all__ = [
    "StaffPayoutFundingFacts",
    "StaffPayoutFundingState",
    "determine_staff_payout_funding_state",
]

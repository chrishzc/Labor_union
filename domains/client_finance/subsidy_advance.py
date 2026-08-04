"""Pure eligibility and recovery rules for a union-funded subsidy advance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text


class SubsidyAdvanceDecisionKind(StrEnum):
    NOT_FIRST_QUARTER_MONTH = "not_first_quarter_month"
    NOT_DUE = "not_due"
    GOVERNMENT_RECEIPT_ALLOCATED = "government_receipt_allocated"
    REVIEW_REQUIRED = "review_required"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class SubsidyAdvanceFacts:
    case_no: str
    completed_on: date
    subsidy_return_due: MoneyNTD
    government_receipt_allocated: MoneyNTD

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 191)
        _require_date(self.completed_on, "completed date")
        _require_positive_money(self.subsidy_return_due, "subsidy return due")
        _require_nonnegative_money(
            self.government_receipt_allocated,
            "government receipt allocated",
        )


@dataclass(frozen=True, slots=True)
class SubsidyAdvanceDecision:
    case_no: str
    refund_due_on: date
    kind: SubsidyAdvanceDecisionKind
    payout_amount: MoneyNTD | None


@dataclass(frozen=True, slots=True)
class SubsidyAdvanceRecovery:
    case_no: str
    advance_entry_identity: str
    government_allocation_identity: str
    amount: MoneyNTD

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 191)
        require_canonical_text(
            self.advance_entry_identity,
            "advance entry identity",
            191,
        )
        require_canonical_text(
            self.government_allocation_identity,
            "government allocation identity",
            191,
        )
        if self.amount.amount <= 0:
            raise ValueError("subsidy_advance_recovery_amount_invalid")


def build_subsidy_advance_decision(
    facts: SubsidyAdvanceFacts,
    business_date: date,
) -> SubsidyAdvanceDecision:
    _require_date(business_date, "business date")
    due_on = subsidy_advance_due_date(facts.completed_on)
    if not is_first_month_of_quarter(facts.completed_on):
        return _decision(facts, due_on, SubsidyAdvanceDecisionKind.NOT_FIRST_QUARTER_MONTH)
    if business_date < due_on:
        return _decision(facts, due_on, SubsidyAdvanceDecisionKind.NOT_DUE)
    if facts.government_receipt_allocated.amount == 0:
        return _decision(facts, due_on, SubsidyAdvanceDecisionKind.READY)
    if facts.government_receipt_allocated == facts.subsidy_return_due:
        return _decision(facts, due_on, SubsidyAdvanceDecisionKind.GOVERNMENT_RECEIPT_ALLOCATED)
    return _decision(facts, due_on, SubsidyAdvanceDecisionKind.REVIEW_REQUIRED)


def build_subsidy_advance_recovery(
    facts: SubsidyAdvanceFacts,
    advance_entry_identity: str,
    government_allocation_identity: str,
    advance_paid: MoneyNTD,
    already_recovered: MoneyNTD,
) -> SubsidyAdvanceRecovery:
    _require_nonnegative_money(advance_paid, "advance paid")
    _require_nonnegative_money(already_recovered, "already recovered")
    if already_recovered.amount:
        raise ValueError("subsidy_advance_already_recovered")
    if advance_paid.amount != facts.government_receipt_allocated.amount:
        raise ValueError("subsidy_advance_settlement_ambiguous")
    return SubsidyAdvanceRecovery(
        facts.case_no,
        advance_entry_identity,
        government_allocation_identity,
        advance_paid,
    )


def is_first_month_of_quarter(value: date) -> bool:
    _require_date(value, "completed date")
    return value.month in {1, 4, 7, 10}


def subsidy_advance_due_date(completed_on: date) -> date:
    _require_date(completed_on, "completed date")
    due_month = completed_on.month + 2
    due_year = completed_on.year + (due_month - 1) // 12
    return date(due_year, ((due_month - 1) % 12) + 1, 15)


def _decision(facts, due_on, kind):
    amount = facts.subsidy_return_due if kind is SubsidyAdvanceDecisionKind.READY else None
    return SubsidyAdvanceDecision(facts.case_no, due_on, kind, amount)


def _require_date(value, field_name: str) -> None:
    if not isinstance(value, date):
        raise TypeError(f"{field_name} must be a date")


def _require_nonnegative_money(value, field_name: str) -> None:
    if not isinstance(value, MoneyNTD) or value.amount < 0:
        raise ValueError(f"{field_name} must be nonnegative integer NTD")


def _require_positive_money(value, field_name: str) -> None:
    if not isinstance(value, MoneyNTD) or value.amount <= 0:
        raise ValueError(f"{field_name} must be positive integer NTD")

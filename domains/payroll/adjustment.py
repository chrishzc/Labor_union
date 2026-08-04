"""Pure Payroll adjustment candidate built from effective assignment facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191


class AdjustmentObligationKind(StrEnum):
    ADJUSTMENT = "adjustment"
    REVERSAL = "reversal"


class AdjustmentDirection(StrEnum):
    PAYABLE_TO_STAFF = "payable_to_staff"
    RECEIVABLE_FROM_STAFF = "receivable_from_staff"


@dataclass(frozen=True, slots=True)
class EffectivePayrollAssignment:
    assignment_id: int
    staff_id: int
    source_obligation_identity: str | None = None
    payout_history_exists: bool = False

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        require_positive_integer(self.staff_id, "staff id")
        if self.source_obligation_identity is not None:
            require_canonical_text(
                self.source_obligation_identity,
                "source obligation identity",
                _IDENTITY_MAXIMUM_LENGTH,
            )
        if not isinstance(self.payout_history_exists, bool):
            raise TypeError("payout history flag must be bool")


@dataclass(frozen=True, slots=True)
class PayrollAdjustmentFacts:
    case_no: str
    payroll_version: int
    due_date: date | None
    effective_assignments: tuple[EffectivePayrollAssignment, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_nonnegative_integer(self.payroll_version, "payroll version")
        if self.due_date is not None and not isinstance(self.due_date, date):
            raise TypeError("staff payment due date must be date")
        _validate_effective_assignments(self.effective_assignments)


@dataclass(frozen=True, slots=True)
class PayrollAdjustmentAllocationIntent:
    assignment_id: int
    amount: MoneyNTD

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        if not isinstance(self.amount, MoneyNTD):
            raise TypeError("payroll adjustment amount must be MoneyNTD")
        if self.amount.is_zero:
            raise ValueError("payroll_adjustment_amount_must_be_nonzero")


@dataclass(frozen=True, slots=True)
class PayrollAdjustmentIntent:
    case_no: str
    source_event_identity: str
    allocations: tuple[PayrollAdjustmentAllocationIntent, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(
            self.source_event_identity,
            "source event identity",
            _IDENTITY_MAXIMUM_LENGTH,
        )
        _validate_allocation_intents(self.allocations)


@dataclass(frozen=True, slots=True)
class PayrollAdjustmentAllocationCandidate:
    assignment_id: int
    staff_id: int
    signed_amount: MoneyNTD
    obligation_identity: str
    obligation_kind: AdjustmentObligationKind
    direction: AdjustmentDirection
    amount_due: MoneyNTD
    source_obligation_identity: str | None
    payout_history_exists: bool


@dataclass(frozen=True, slots=True)
class PayrollAdjustmentCandidate:
    case_no: str
    source_event_identity: str
    adjustment_identity: str
    amount: MoneyNTD
    due_date: date
    allocations: tuple[PayrollAdjustmentAllocationCandidate, ...]
    fingerprint: PreviewFingerprint


# Kept whole so validation, conservation, and fingerprint use one candidate snapshot.
def build_payroll_adjustment_candidate(
    facts: PayrollAdjustmentFacts,
    intent: PayrollAdjustmentIntent,
) -> PayrollAdjustmentCandidate:
    _validate_case_identity(facts, intent)
    due_date = _require_due_date(facts)
    assignments = {item.assignment_id: item for item in facts.effective_assignments}
    allocations = _build_allocations(intent, assignments)
    amount = MoneyNTD(sum(item.signed_amount.amount for item in allocations))
    if amount.is_zero:
        raise ValueError("payroll_adjustment_total_must_be_nonzero")
    fingerprint = fingerprint_payload(
        _candidate_payload(facts, intent, due_date, allocations, amount)
    )
    return PayrollAdjustmentCandidate(
        facts.case_no,
        intent.source_event_identity,
        f"payroll-adjustment:{facts.case_no}:{fingerprint.value[:24]}",
        amount,
        due_date,
        allocations,
        fingerprint,
    )


def _build_allocations(intent, assignments):
    candidates = []
    for allocation in intent.allocations:
        assignment = assignments.get(allocation.assignment_id)
        if assignment is None:
            raise ValueError("payroll_adjustment_assignment_not_effective")
        candidates.append(_allocation_candidate(intent, allocation, assignment))
    return tuple(candidates)


# Kept whole so one signed amount determines every obligation field together.
def _allocation_candidate(intent, allocation, assignment):
    positive = allocation.amount.amount > 0
    kind = (
        AdjustmentObligationKind.ADJUSTMENT
        if positive
        else AdjustmentObligationKind.REVERSAL
    )
    direction = (
        AdjustmentDirection.PAYABLE_TO_STAFF
        if positive
        else AdjustmentDirection.RECEIVABLE_FROM_STAFF
    )
    return PayrollAdjustmentAllocationCandidate(
        allocation.assignment_id,
        assignment.staff_id,
        allocation.amount,
        _obligation_identity(intent, allocation),
        kind,
        direction,
        MoneyNTD(abs(allocation.amount.amount)),
        assignment.source_obligation_identity,
        assignment.payout_history_exists,
    )


def _candidate_payload(facts, intent, due_date, allocations, amount):
    return {
        "case_no": facts.case_no,
        "payroll_version": facts.payroll_version,
        "source_event_identity": intent.source_event_identity,
        "due_date": due_date.isoformat(),
        "amount_ntd": amount.amount,
        "allocations": tuple(_allocation_payload(item) for item in allocations),
    }


def _allocation_payload(allocation):
    return {
        "assignment_id": allocation.assignment_id,
        "staff_id": allocation.staff_id,
        "amount_ntd": allocation.signed_amount.amount,
        "obligation_kind": allocation.obligation_kind.value,
        "direction": allocation.direction.value,
        "source_obligation_identity": allocation.source_obligation_identity,
        "payout_history_exists": allocation.payout_history_exists,
    }


def _obligation_identity(intent, allocation):
    seed = fingerprint_payload(
        {
            "case_no": intent.case_no,
            "source_event_identity": intent.source_event_identity,
            "assignment_id": allocation.assignment_id,
            "amount_ntd": allocation.amount.amount,
        }
    )
    return f"staff-obligation:adjustment:{seed.value[:32]}"


def _validate_case_identity(facts, intent) -> None:
    if facts.case_no != intent.case_no:
        raise ValueError("invalid_payroll_facts")


def _require_due_date(facts) -> date:
    if facts.due_date is None:
        raise ValueError("staff_payment_due_date_required")
    return facts.due_date


def _validate_effective_assignments(assignments) -> None:
    if not isinstance(assignments, tuple):
        raise TypeError("effective assignments must be a tuple")
    identities = tuple(item.assignment_id for item in assignments)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("invalid_payroll_facts")


def _validate_allocation_intents(allocations) -> None:
    if not isinstance(allocations, tuple) or not allocations:
        raise ValueError("payroll_adjustment_allocations_required")
    identities = tuple(item.assignment_id for item in allocations)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("payroll_adjustment_allocations_must_be_unique")


__all__ = [
    "AdjustmentDirection",
    "AdjustmentObligationKind",
    "EffectivePayrollAssignment",
    "PayrollAdjustmentAllocationCandidate",
    "PayrollAdjustmentAllocationIntent",
    "PayrollAdjustmentCandidate",
    "PayrollAdjustmentFacts",
    "PayrollAdjustmentIntent",
    "build_payroll_adjustment_candidate",
]

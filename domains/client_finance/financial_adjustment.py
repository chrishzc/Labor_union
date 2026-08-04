"""Client-only and cross-domain financial adjustment candidates."""

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


class FinancialAdjustmentSource(StrEnum):
    PREVIEW_RECALCULATION = "preview_recalculation"
    MANUAL_EXTRA = "manual_extra"


class FinancialAdjustmentScope(StrEnum):
    CLIENT_ONLY = "client_only"
    CLIENT_AND_STAFF = "client_and_staff"


class ClientAdjustmentDirection(StrEnum):
    RECEIVABLE_FROM_CLIENT = "receivable_from_client"
    PAYABLE_TO_CLIENT = "payable_to_client"


class StaffAdjustmentDirection(StrEnum):
    PAYABLE_TO_STAFF = "payable_to_staff"
    RECEIVABLE_FROM_STAFF = "receivable_from_staff"


@dataclass(frozen=True, slots=True)
class FinancialAdjustmentAssignmentFact:
    assignment_id: int
    staff_id: int
    due_date: date | None
    cancelled: bool = False

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        require_positive_integer(self.staff_id, "staff id")
        if self.due_date is not None and not isinstance(self.due_date, date):
            raise TypeError("staff adjustment due date must be date")
        if not isinstance(self.cancelled, bool):
            raise TypeError("assignment cancelled flag must be bool")


@dataclass(frozen=True, slots=True)
class FinancialAdjustmentReversalTarget:
    adjustment_identity: str
    case_no: str
    amount_delta: MoneyNTD
    reversed_amount_delta: MoneyNTD
    scope: FinancialAdjustmentScope = FinancialAdjustmentScope.CLIENT_AND_STAFF

    def __post_init__(self) -> None:
        _validate_identity(self.adjustment_identity, "adjustment identity")
        _validate_identity(self.case_no, "case number")
        _require_nonzero_money(self.amount_delta, "target amount")
        if not isinstance(self.reversed_amount_delta, MoneyNTD):
            raise TypeError("reversed adjustment amount must be MoneyNTD")
        _validate_scope(self.scope)


@dataclass(frozen=True, slots=True)
class FinancialAdjustmentFacts:
    case_no: str
    client_account_version: int
    payroll_version: int
    assignments: tuple[FinancialAdjustmentAssignmentFact, ...]
    reversal_target: FinancialAdjustmentReversalTarget | None = None

    def __post_init__(self) -> None:
        _validate_identity(self.case_no, "case number")
        require_nonnegative_integer(
            self.client_account_version,
            "client account version",
        )
        require_nonnegative_integer(self.payroll_version, "payroll version")
        _validate_assignments(self.assignments)


@dataclass(frozen=True, slots=True)
class FinancialAdjustmentAllocationIntent:
    assignment_id: int
    amount_delta: MoneyNTD

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        _require_nonzero_money(self.amount_delta, "assignment adjustment amount")


@dataclass(frozen=True, slots=True)
class FinancialAdjustmentIntent:
    case_no: str
    source_type: FinancialAdjustmentSource
    source_event_identity: str
    amount_delta: MoneyNTD
    assignment_allocations: tuple[FinancialAdjustmentAllocationIntent, ...]
    reason: str | None = None
    reversal_of_adjustment_identity: str | None = None
    scope: FinancialAdjustmentScope = FinancialAdjustmentScope.CLIENT_AND_STAFF

    def __post_init__(self) -> None:
        _validate_identity(self.case_no, "case number")
        _validate_identity(self.source_event_identity, "source event identity")
        _validate_scope(self.scope)
        _require_nonzero_money(self.amount_delta, "financial adjustment amount")
        _validate_allocation_intents(self.scope, self.assignment_allocations)
        _validate_reason(self.source_type, self.reason)
        if self.reversal_of_adjustment_identity is not None:
            _validate_identity(
                self.reversal_of_adjustment_identity,
                "reversal target identity",
            )


@dataclass(frozen=True, slots=True)
class StaffAdjustmentAllocationCandidate:
    assignment_id: int
    staff_id: int
    amount_delta: MoneyNTD
    direction: StaffAdjustmentDirection
    obligation_identity: str
    due_date: date


@dataclass(frozen=True, slots=True)
class FinancialAdjustmentCandidate:
    adjustment_identity: str
    case_no: str
    source_type: FinancialAdjustmentSource
    source_event_identity: str
    scope: FinancialAdjustmentScope
    amount_delta: MoneyNTD
    client_direction: ClientAdjustmentDirection
    client_obligation_identity: str
    assignment_allocations: tuple[StaffAdjustmentAllocationCandidate, ...]
    reason: str | None
    reversal_of_adjustment_identity: str | None
    fingerprint: PreviewFingerprint


# Kept cohesive so both accounting sides derive from one immutable candidate.
def build_financial_adjustment_candidate(
    facts: FinancialAdjustmentFacts,
    intent: FinancialAdjustmentIntent,
) -> FinancialAdjustmentCandidate:
    _validate_case(facts, intent)
    allocations = _build_candidate_allocations(facts, intent)
    _validate_reversal(facts, intent)
    candidate_fingerprint = fingerprint_payload(
        _candidate_payload(facts, intent, allocations)
    )
    adjustment_identity = (
        f"financial-adjustment:{intent.case_no}:{candidate_fingerprint.value[:24]}"
    )
    return FinancialAdjustmentCandidate(
        adjustment_identity,
        intent.case_no,
        intent.source_type,
        intent.source_event_identity,
        intent.scope,
        intent.amount_delta,
        _client_direction(intent.amount_delta),
        f"client-obligation:adjustment:{candidate_fingerprint.value[:32]}",
        allocations,
        intent.reason,
        intent.reversal_of_adjustment_identity,
        candidate_fingerprint,
    )


def _build_candidate_allocations(facts, intent):
    if intent.scope is FinancialAdjustmentScope.CLIENT_ONLY:
        return ()
    assignment_index = {item.assignment_id: item for item in facts.assignments}
    allocations = _build_allocations(intent, assignment_index)
    _require_conservation(intent, allocations)
    return allocations


def _build_allocations(intent, assignment_index):
    candidates = []
    for allocation in intent.assignment_allocations:
        assignment = assignment_index.get(allocation.assignment_id)
        if assignment is None or assignment.cancelled:
            raise ValueError("financial_adjustment_assignment_not_effective")
        if assignment.due_date is None:
            raise ValueError("staff_payment_due_date_required")
        candidates.append(_allocation_candidate(intent, allocation, assignment))
    return tuple(candidates)


# Kept whole so one signed amount determines identity, direction, and obligation.
def _allocation_candidate(intent, allocation, assignment):
    seed = fingerprint_payload(
        {
            "case_no": intent.case_no,
            "source_event_identity": intent.source_event_identity,
            "assignment_id": allocation.assignment_id,
            "amount_delta_ntd": allocation.amount_delta.amount,
        }
    )
    direction = (
        StaffAdjustmentDirection.PAYABLE_TO_STAFF
        if allocation.amount_delta.amount > 0
        else StaffAdjustmentDirection.RECEIVABLE_FROM_STAFF
    )
    return StaffAdjustmentAllocationCandidate(
        allocation.assignment_id,
        assignment.staff_id,
        allocation.amount_delta,
        direction,
        f"staff-obligation:financial-adjustment:{seed.value[:32]}",
        assignment.due_date,
    )


def _require_conservation(intent, allocations) -> None:
    staff_delta = sum(item.amount_delta.amount for item in allocations)
    if staff_delta != intent.amount_delta.amount:
        raise ValueError("financial_adjustment_not_conserved")


def _validate_reversal(facts, intent) -> None:
    target_identity = intent.reversal_of_adjustment_identity
    target = facts.reversal_target
    if target_identity is None and target is None:
        return
    if target_identity is None or target is None:
        raise ValueError("financial_adjustment_reversal_target_invalid")
    identity_matches = target.adjustment_identity == target_identity
    if not identity_matches or target.case_no != intent.case_no:
        raise ValueError("financial_adjustment_reversal_target_invalid")
    if target.scope is not intent.scope:
        raise ValueError("financial_adjustment_reversal_scope_mismatch")
    if target.amount_delta.amount * intent.amount_delta.amount >= 0:
        raise ValueError("financial_adjustment_reversal_direction_invalid")
    remaining = abs(target.amount_delta.amount + target.reversed_amount_delta.amount)
    if abs(intent.amount_delta.amount) > remaining:
        raise ValueError("financial_adjustment_reversal_amount_exceeded")


def _candidate_payload(facts, intent, allocations):
    payload = {
        "case_no": intent.case_no,
        "client_account_version": facts.client_account_version,
        "scope": intent.scope.value,
        "source_type": intent.source_type.value,
        "source_event_identity": intent.source_event_identity,
        "amount_delta_ntd": intent.amount_delta.amount,
        "reason": intent.reason,
        "reversal_of": intent.reversal_of_adjustment_identity,
        "allocations": tuple(_allocation_payload(item) for item in allocations),
    }
    if intent.scope is FinancialAdjustmentScope.CLIENT_AND_STAFF:
        payload["payroll_version"] = facts.payroll_version
    return payload


def _allocation_payload(allocation):
    return {
        "assignment_id": allocation.assignment_id,
        "staff_id": allocation.staff_id,
        "amount_delta_ntd": allocation.amount_delta.amount,
        "direction": allocation.direction.value,
        "due_date": allocation.due_date.isoformat(),
    }


def _client_direction(amount):
    if amount.amount > 0:
        return ClientAdjustmentDirection.RECEIVABLE_FROM_CLIENT
    return ClientAdjustmentDirection.PAYABLE_TO_CLIENT


def _validate_case(facts, intent) -> None:
    if facts.case_no != intent.case_no:
        raise ValueError("client_finance_identity_ambiguous")


def _validate_assignments(assignments) -> None:
    if not isinstance(assignments, tuple):
        raise TypeError("financial adjustment assignments must be a tuple")
    identities = tuple(item.assignment_id for item in assignments)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("invalid_financial_adjustment_facts")


def _validate_allocation_intents(scope, allocations) -> None:
    if not isinstance(allocations, tuple):
        raise TypeError("financial adjustment allocations must be a tuple")
    if scope is FinancialAdjustmentScope.CLIENT_ONLY:
        if allocations:
            raise ValueError("client_only_adjustment_allocations_forbidden")
        return
    if not allocations:
        raise ValueError("financial_adjustment_allocations_required")
    identities = tuple(item.assignment_id for item in allocations)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("financial_adjustment_allocations_must_be_unique")


def _validate_reason(source_type, reason) -> None:
    if source_type is FinancialAdjustmentSource.MANUAL_EXTRA:
        require_canonical_text(reason, "financial adjustment reason", 255)
        return
    if reason is not None:
        raise ValueError("preview_recalculation_reason_forbidden")


def _validate_scope(scope) -> None:
    if not isinstance(scope, FinancialAdjustmentScope):
        raise TypeError("financial adjustment scope must be typed")


def _validate_identity(value, field_name) -> None:
    require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)


def _require_nonzero_money(value, field_name) -> None:
    if not isinstance(value, MoneyNTD) or value.is_zero:
        raise ValueError(f"{field_name} must be nonzero integer NTD")


__all__ = [
    "ClientAdjustmentDirection",
    "FinancialAdjustmentAllocationIntent",
    "FinancialAdjustmentAssignmentFact",
    "FinancialAdjustmentCandidate",
    "FinancialAdjustmentFacts",
    "FinancialAdjustmentIntent",
    "FinancialAdjustmentReversalTarget",
    "FinancialAdjustmentScope",
    "FinancialAdjustmentSource",
    "StaffAdjustmentAllocationCandidate",
    "StaffAdjustmentDirection",
    "build_financial_adjustment_candidate",
]

"""Pure planning, submission, approval, and cursor contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.government_subsidy.ledger import (
    AllocationIntent,
    ClaimBatchFacts,
    ClaimBatchIdentity,
    GovernmentSubsidyBatchStatus,
    GovernmentSubsidyDomainError,
    GovernmentSubsidyErrorCode,
    OfficialAssignmentServiceFacts,
    reduce_batch_status,
    validate_approval_amounts,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_positive_integer


class GovernmentSubsidyClaimMutationKind(StrEnum):
    PLAN = "plan"
    SUBMIT = "submit"
    APPROVAL = "approval"


@dataclass(frozen=True, slots=True)
class ClaimPlanningIntent:
    identity: ClaimBatchIdentity


@dataclass(frozen=True, slots=True)
class ClaimPlanningSourceItem:
    assignment: OfficialAssignmentServiceFacts
    unit_price_ntd: MoneyNTD

    def __post_init__(self) -> None:
        if not isinstance(self.assignment, OfficialAssignmentServiceFacts):
            raise TypeError("claim planning assignment is invalid")
        if not isinstance(self.unit_price_ntd, MoneyNTD):
            raise TypeError("claim planning unit price is invalid")
        if self.unit_price_ntd.amount <= 0:
            _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)


@dataclass(frozen=True, slots=True)
class ClaimPlanningFacts:
    intent: ClaimPlanningIntent
    sources: tuple[ClaimPlanningSourceItem, ...]
    existing_batch_id: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intent, ClaimPlanningIntent):
            raise TypeError("claim planning intent is invalid")
        if not isinstance(self.sources, tuple) or not self.sources:
            _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)
        if self.existing_batch_id is not None:
            require_positive_integer(self.existing_batch_id, "batch id")


@dataclass(frozen=True, slots=True)
class PlannedClaimItem:
    assignment_id: int
    case_no: str
    staff_id: int
    claimed_hours: int
    unit_price_ntd: MoneyNTD
    requested_amount_ntd: MoneyNTD


@dataclass(frozen=True, slots=True)
class ClaimPlanningCandidate:
    kind: GovernmentSubsidyClaimMutationKind
    identity: ClaimBatchIdentity
    expected_batch_version: int
    resulting_batch_version: int
    items: tuple[PlannedClaimItem, ...]
    requested_total_ntd: MoneyNTD
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ClaimSubmissionCandidate:
    kind: GovernmentSubsidyClaimMutationKind
    batch: ClaimBatchFacts
    expected_batch_version: int
    resulting_batch_version: int
    before_status: GovernmentSubsidyBatchStatus
    after_status: GovernmentSubsidyBatchStatus
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ClaimApprovalIntent:
    batch_id: int
    item_approvals: tuple[AllocationIntent, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.batch_id, "batch id")
        if not isinstance(self.item_approvals, tuple):
            raise TypeError("government subsidy approvals must be a tuple")


@dataclass(frozen=True, slots=True)
class ClaimApprovalCandidate:
    kind: GovernmentSubsidyClaimMutationKind
    batch: ClaimBatchFacts
    intent: ClaimApprovalIntent
    expected_batch_version: int
    resulting_batch_version: int
    approved_total_ntd: MoneyNTD
    before_status: GovernmentSubsidyBatchStatus
    after_status: GovernmentSubsidyBatchStatus
    fingerprint: PreviewFingerprint


GovernmentSubsidyClaimCandidate = (
    ClaimPlanningCandidate
    | ClaimSubmissionCandidate
    | ClaimApprovalCandidate
)


@dataclass(frozen=True, slots=True)
class ClaimBatchCursorPage:
    batches: tuple[ClaimBatchFacts, ...]
    next_cursor: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.batches, tuple):
            raise TypeError("government subsidy batches must be a tuple")
        if self.next_cursor is not None:
            require_positive_integer(self.next_cursor, "next cursor")


def build_claim_planning_candidate(
    facts: ClaimPlanningFacts,
) -> ClaimPlanningCandidate:
    if facts.existing_batch_id is not None:
        _raise(GovernmentSubsidyErrorCode.BATCH_CANDIDATE_NOT_UNIQUE)
    items = tuple(
        sorted(
            (_planned_item(source) for source in facts.sources),
            key=lambda item: item.assignment_id,
        )
    )
    _validate_unique_assignments(items)
    requested_total = _sum_money(
        item.requested_amount_ntd for item in items
    )
    payload = {
        "kind": GovernmentSubsidyClaimMutationKind.PLAN.value,
        "batch_identity": facts.intent.identity.value,
        "expected_batch_version": 0,
        "items": tuple(_planned_item_payload(item) for item in items),
        "requested_total_ntd": requested_total.amount,
    }
    return ClaimPlanningCandidate(
        GovernmentSubsidyClaimMutationKind.PLAN,
        facts.intent.identity,
        0,
        1,
        items,
        requested_total,
        fingerprint_payload(payload),
    )


def build_claim_submission_candidate(
    batch: ClaimBatchFacts,
) -> ClaimSubmissionCandidate:
    before_status = reduce_batch_status(batch)
    if before_status is not GovernmentSubsidyBatchStatus.DRAFT:
        _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)
    payload = {
        "kind": GovernmentSubsidyClaimMutationKind.SUBMIT.value,
        "batch": _batch_payload(batch),
        "after_status": GovernmentSubsidyBatchStatus.SUBMITTED.value,
    }
    return ClaimSubmissionCandidate(
        GovernmentSubsidyClaimMutationKind.SUBMIT,
        batch,
        batch.aggregate_version,
        batch.aggregate_version + 1,
        before_status,
        GovernmentSubsidyBatchStatus.SUBMITTED,
        fingerprint_payload(payload),
    )


def build_claim_approval_candidate(
    batch: ClaimBatchFacts,
    intent: ClaimApprovalIntent,
) -> ClaimApprovalCandidate:
    if batch.batch_id != intent.batch_id:
        _raise(GovernmentSubsidyErrorCode.APPROVAL_INVALID)
    if reduce_batch_status(batch) is not GovernmentSubsidyBatchStatus.SUBMITTED:
        _raise(GovernmentSubsidyErrorCode.APPROVAL_INVALID)
    approved_total = _approved_total(batch, intent)
    payload = {
        "kind": GovernmentSubsidyClaimMutationKind.APPROVAL.value,
        "batch": _batch_payload(batch),
        "approvals": tuple(
            (item.target_identity, item.amount_ntd.amount)
            for item in intent.item_approvals
        ),
        "approved_total_ntd": approved_total.amount,
    }
    return ClaimApprovalCandidate(
        GovernmentSubsidyClaimMutationKind.APPROVAL,
        batch,
        intent,
        batch.aggregate_version,
        batch.aggregate_version + 1,
        approved_total,
        GovernmentSubsidyBatchStatus.SUBMITTED,
        GovernmentSubsidyBatchStatus.APPROVED,
        fingerprint_payload(payload),
    )


def _planned_item(source):
    assignment = source.assignment
    if not assignment.effective:
        _raise(GovernmentSubsidyErrorCode.ASSIGNMENT_FACTS_STALE)
    requested = source.unit_price_ntd * assignment.official_service_hours
    return PlannedClaimItem(
        assignment.assignment_id,
        assignment.case_no,
        assignment.staff_id,
        assignment.official_service_hours,
        source.unit_price_ntd,
        requested,
    )


def _validate_unique_assignments(items):
    assignment_ids = tuple(item.assignment_id for item in items)
    if len(assignment_ids) != len(set(assignment_ids)):
        _raise(GovernmentSubsidyErrorCode.CLAIM_FACTS_INVALID)


def _approved_total(batch, intent):
    try:
        return validate_approval_amounts(
            batch.items,
            intent.item_approvals,
        )
    except GovernmentSubsidyDomainError as error:
        raise GovernmentSubsidyDomainError(
            GovernmentSubsidyErrorCode.APPROVAL_INVALID,
            error.blockers,
        ) from error


def _planned_item_payload(item):
    return {
        "assignment_id": item.assignment_id,
        "case_no": item.case_no,
        "staff_id": item.staff_id,
        "claimed_hours": item.claimed_hours,
        "unit_price_ntd": item.unit_price_ntd.amount,
        "requested_amount_ntd": item.requested_amount_ntd.amount,
    }


def _batch_payload(batch):
    return {
        "batch_id": batch.batch_id,
        "identity": batch.identity.value,
        "aggregate_version": batch.aggregate_version,
        "submitted": batch.submitted,
        "approval_complete": batch.approval_complete,
        "items": tuple(
            {
                "item_id": item.item_id,
                "assignment_id": item.assignment_id,
                "requested_amount_ntd": item.requested_amount_ntd.amount,
            }
            for item in batch.items
        ),
    }


def _sum_money(values):
    return MoneyNTD(sum(value.amount for value in values))


def _raise(code):
    raise GovernmentSubsidyDomainError(code)


__all__ = [
    "ClaimApprovalCandidate",
    "ClaimApprovalIntent",
    "ClaimBatchCursorPage",
    "ClaimPlanningCandidate",
    "ClaimPlanningFacts",
    "ClaimPlanningIntent",
    "ClaimPlanningSourceItem",
    "ClaimSubmissionCandidate",
    "GovernmentSubsidyClaimCandidate",
    "GovernmentSubsidyClaimMutationKind",
    "PlannedClaimItem",
    "build_claim_approval_candidate",
    "build_claim_planning_candidate",
    "build_claim_submission_candidate",
]

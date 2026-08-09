"""Canonical Government Subsidy claim planning, submission, and approval workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol, TypeAlias

from domains.government_subsidy.claims import (
    ClaimApprovalCandidate,
    ClaimApprovalIntent,
    ClaimBatchCursorPage,
    ClaimBatchFacts,
    ClaimPlanningCandidate,
    ClaimPlanningFacts,
    ClaimPlanningIntent,
    ClaimSubmissionCandidate,
    GovernmentSubsidyClaimCandidate,
    GovernmentSubsidyClaimMutationKind,
    build_claim_approval_candidate,
    build_claim_planning_candidate,
    build_claim_submission_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_positive_integer

_MAXIMUM_PAGE_SIZE = 100
_REASON_MAXIMUM_LENGTH = 500


class GovernmentSubsidyClaimState(StrEnum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class ClaimSubmissionIntent:
    batch_id: int


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyClaimPreview:
    candidate: GovernmentSubsidyClaimCandidate
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ClaimPlanningApplyRequest:
    intent: ClaimPlanningIntent
    expected_batch_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ClaimSubmissionApplyRequest:
    intent: ClaimSubmissionIntent
    expected_batch_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ClaimApprovalApplyRequest:
    intent: ClaimApprovalIntent
    expected_batch_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


GovernmentSubsidyClaimApplyRequest: TypeAlias = (
    ClaimPlanningApplyRequest | ClaimSubmissionApplyRequest | ClaimApprovalApplyRequest
)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyClaimReceipt:
    kind: GovernmentSubsidyClaimMutationKind
    batch_id: int
    batch_version: int
    status: str
    item_count: int
    total_ntd: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredGovernmentSubsidyClaimReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: GovernmentSubsidyClaimReceipt


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyClaimReceiptCommand:
    request: GovernmentSubsidyClaimApplyRequest
    stored_receipt: StoredGovernmentSubsidyClaimReceipt


class GovernmentSubsidyClaimRepository(Protocol):
    def load_claim_planning_facts(self, intent: ClaimPlanningIntent, *, lock: bool) -> ClaimPlanningFacts: ...
    def load_batch(self, batch_id: int, *, lock: bool = False) -> ClaimBatchFacts: ...
    def list_batches(self, cursor: int | None, limit: int) -> ClaimBatchCursorPage: ...
    def claim_command(self, request: GovernmentSubsidyClaimApplyRequest, command_fingerprint: PreviewFingerprint) -> GovernmentSubsidyClaimState: ...
    def find_claim_receipt(self, key: IdempotencyKey, *, for_update: bool) -> StoredGovernmentSubsidyClaimReceipt | None: ...
    def create_claim_batch(self, request: ClaimPlanningApplyRequest, candidate: ClaimPlanningCandidate) -> int: ...
    def append_claim_submission(self, request: ClaimSubmissionApplyRequest, candidate: ClaimSubmissionCandidate) -> None: ...
    def append_claim_approval(self, request: ClaimApprovalApplyRequest, candidate: ClaimApprovalCandidate) -> None: ...
    def append_claim_outbox(self, request: GovernmentSubsidyClaimApplyRequest, candidate: GovernmentSubsidyClaimCandidate, batch_id: int) -> None: ...
    def save_claim_receipt(self, command: GovernmentSubsidyClaimReceiptCommand) -> None: ...


class UnitOfWork(Protocol):
    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, exception_type, exception, traceback) -> bool: ...
    def commit(self) -> None: ...


class GovernmentSubsidyClaimWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class GovernmentSubsidyClaimWorkflow:
    def __init__(self, repository: GovernmentSubsidyClaimRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def list_batches(self, cursor: int | None, limit: int) -> ClaimBatchCursorPage:
        _validate_page(cursor, limit)
        return self._repository.list_batches(cursor, limit)

    def query_batch(self, batch_id: int) -> ClaimBatchFacts:
        return self._repository.load_batch(batch_id)

    def preview_plan(self, intent: ClaimPlanningIntent) -> GovernmentSubsidyClaimPreview:
        facts = self._repository.load_claim_planning_facts(intent, lock=False)
        return _preview(build_claim_planning_candidate(facts))

    def preview_submission(self, intent: ClaimSubmissionIntent) -> GovernmentSubsidyClaimPreview:
        return _preview(build_claim_submission_candidate(self._repository.load_batch(intent.batch_id)))

    def preview_approval(self, intent: ClaimApprovalIntent) -> GovernmentSubsidyClaimPreview:
        return _preview(build_claim_approval_candidate(self._repository.load_batch(intent.batch_id), intent))

    def apply(self, request: GovernmentSubsidyClaimApplyRequest) -> GovernmentSubsidyClaimReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self._apply_in_current_transaction(request)
            unit_of_work.commit()
            return receipt

    def _apply_in_current_transaction(self, request):
        command_fingerprint = _command_fingerprint(request)
        replay = self._claim_or_replay(request, command_fingerprint)
        if replay is not None:
            return replay
        preview = self._fresh_preview(request)
        receipt = self._persist(request, preview)
        self._repository.save_claim_receipt(GovernmentSubsidyClaimReceiptCommand(request, StoredGovernmentSubsidyClaimReceipt(command_fingerprint, receipt)))
        return receipt

    def _claim_or_replay(self, request, command_fingerprint):
        state = self._repository.claim_command(request, command_fingerprint)
        if state is GovernmentSubsidyClaimState.MISMATCH:
            raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was used with a different command.")
        stored = self._repository.find_claim_receipt(request.idempotency_key, for_update=True)
        if stored is not None:
            return _matched_receipt(request, command_fingerprint, stored)
        if state is GovernmentSubsidyClaimState.MATCHED:
            raise _workflow_error(request, ErrorCategory.INTERNAL, "idempotency_evidence_incomplete", "Command claim exists without its receipt.")
        return None

    def _fresh_preview(self, request):
        if isinstance(request, ClaimPlanningApplyRequest):
            preview = _preview(build_claim_planning_candidate(self._repository.load_claim_planning_facts(request.intent, lock=True)))
        else:
            preview = _batch_mutation_preview(request, self._repository.load_batch(request.intent.batch_id, lock=True))
        _validate_fresh_preview(request, preview)
        return preview

    def _persist(self, request, preview):
        candidate = preview.candidate
        if isinstance(request, ClaimPlanningApplyRequest):
            batch_id = self._repository.create_claim_batch(request, candidate)
        else:
            batch_id = candidate.batch.batch_id
            _persist_existing_batch(self._repository, request, candidate)
        self._repository.append_claim_outbox(request, candidate, batch_id)
        return _build_receipt(candidate, batch_id)


def _batch_mutation_preview(request, batch):
    if isinstance(request, ClaimSubmissionApplyRequest):
        return _preview(build_claim_submission_candidate(batch))
    return _preview(build_claim_approval_candidate(batch, request.intent))


def _persist_existing_batch(repository, request, candidate) -> None:
    if isinstance(request, ClaimSubmissionApplyRequest):
        repository.append_claim_submission(request, candidate)
        return
    repository.append_claim_approval(request, candidate)


def _preview(candidate) -> GovernmentSubsidyClaimPreview:
    return GovernmentSubsidyClaimPreview(candidate, candidate.fingerprint)


def _validate_fresh_preview(request, preview) -> None:
    current = preview.candidate.expected_batch_version
    if request.expected_batch_version.value != current:
        raise GovernmentSubsidyClaimWorkflowError(TypedError(ErrorCategory.CONFLICT, "government_subsidy_version_conflict", "Government Subsidy batch version changed before Apply.", request.correlation_id, current_version=ExpectedVersion(current)))
    if request.preview_fingerprint != preview.fingerprint:
        raise _workflow_error(request, ErrorCategory.CONFLICT, "stale_preview", "Government Subsidy claim facts changed after Preview.")


def _build_receipt(candidate, batch_id: int) -> GovernmentSubsidyClaimReceipt:
    if isinstance(candidate, ClaimPlanningCandidate):
        status, item_count, total_ntd = "draft", len(candidate.items), candidate.requested_total_ntd.amount
    elif isinstance(candidate, ClaimSubmissionCandidate):
        status, item_count, total_ntd = candidate.after_status.value, len(candidate.batch.items), candidate.batch.requested_total_ntd.amount
    else:
        status, item_count, total_ntd = candidate.after_status.value, len(candidate.batch.items), candidate.approved_total_ntd.amount
    return GovernmentSubsidyClaimReceipt(candidate.kind, batch_id, candidate.resulting_batch_version, status, item_count, total_ntd, candidate.fingerprint)


def _command_fingerprint(request) -> PreviewFingerprint:
    return fingerprint_payload({"kind": _request_kind(request).value, "intent": _intent_payload(request.intent), "expected_batch_version": request.expected_batch_version.value, "preview_fingerprint": request.preview_fingerprint.value, "actor": request.actor.actor_id, "reason": request.reason})


def _request_kind(request) -> GovernmentSubsidyClaimMutationKind:
    if isinstance(request, ClaimPlanningApplyRequest):
        return GovernmentSubsidyClaimMutationKind.PLAN
    if isinstance(request, ClaimSubmissionApplyRequest):
        return GovernmentSubsidyClaimMutationKind.SUBMIT
    return GovernmentSubsidyClaimMutationKind.APPROVAL


def _intent_payload(intent):
    if isinstance(intent, ClaimPlanningIntent):
        return {"identity": intent.identity.value}
    if isinstance(intent, ClaimSubmissionIntent):
        return {"batch_id": intent.batch_id}
    return {"batch_id": intent.batch_id, "item_approvals": tuple((item.target_identity, item.amount_ntd.amount) for item in intent.item_approvals)}


def _matched_receipt(request, command_fingerprint, stored):
    if stored.command_fingerprint == command_fingerprint:
        return stored.receipt
    raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was used with a different command.")


def _validate_apply_request(request, intent_type) -> None:
    if not isinstance(request.intent, intent_type):
        raise TypeError("government subsidy claim intent is invalid")
    require_canonical_text(request.reason, "government subsidy reason", _REASON_MAXIMUM_LENGTH)


def _validate_page(cursor: int | None, limit: int) -> None:
    if cursor is not None:
        require_positive_integer(cursor, "batch cursor")
    require_positive_integer(limit, "batch page size")
    if limit > _MAXIMUM_PAGE_SIZE:
        raise ValueError("government subsidy page size exceeds maximum")


def _workflow_error(request, category, code: str, message: str) -> GovernmentSubsidyClaimWorkflowError:
    return GovernmentSubsidyClaimWorkflowError(TypedError(category, code, message, request.correlation_id))


__all__ = [
    "ClaimApprovalApplyRequest", "ClaimPlanningApplyRequest", "ClaimSubmissionApplyRequest",
    "ClaimSubmissionIntent", "GovernmentSubsidyClaimApplyRequest", "GovernmentSubsidyClaimPreview",
    "GovernmentSubsidyClaimReceipt", "GovernmentSubsidyClaimReceiptCommand", "GovernmentSubsidyClaimRepository",
    "GovernmentSubsidyClaimState", "GovernmentSubsidyClaimWorkflow", "GovernmentSubsidyClaimWorkflowError",
    "StoredGovernmentSubsidyClaimReceipt",
]

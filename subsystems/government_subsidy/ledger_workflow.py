"""Preview and atomic Apply workflows for Government Subsidy ledger events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol, TypeAlias

from domains.government_subsidy.ledger import (
    ClaimBatchFacts,
    GovernmentBankFact,
    GovernmentSubsidyLedgerCandidate,
    GovernmentSubsidyLedgerKind,
    ReceiptIntent,
    ReversalIntent,
    SourceReceiptFacts,
    build_receipt_candidate,
    build_reversal_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text

_REASON_MAXIMUM_LENGTH = 500


class GovernmentSubsidyClaimState(StrEnum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReceiptContext:
    bank_fact: GovernmentBankFact
    batches: tuple[ClaimBatchFacts, ...]


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReversalContext:
    bank_fact: GovernmentBankFact
    batch: ClaimBatchFacts
    source_receipt: SourceReceiptFacts


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyPreview:
    candidate: GovernmentSubsidyLedgerCandidate
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReceiptApplyRequest:
    intent: ReceiptIntent
    expected_batch_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_apply_request(self, ReceiptIntent)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReversalApplyRequest:
    intent: ReversalIntent
    expected_batch_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_apply_request(self, ReversalIntent)


GovernmentSubsidyApplyRequest: TypeAlias = (
    GovernmentSubsidyReceiptApplyRequest | GovernmentSubsidyReversalApplyRequest
)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyCommandReceipt:
    kind: GovernmentSubsidyLedgerKind
    transaction_id: int
    batch_id: int
    batch_version: int
    bank_fact_identity: str
    amount_ntd: int
    allocation_count: int
    status: str
    outstanding_ntd: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredGovernmentSubsidyReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: GovernmentSubsidyCommandReceipt


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyProjectionCommand:
    candidate: GovernmentSubsidyLedgerCandidate


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReceiptPersistenceCommand:
    request: GovernmentSubsidyApplyRequest
    stored_receipt: StoredGovernmentSubsidyReceipt


class GovernmentSubsidyWorkflowRepository(Protocol):
    def load_receipt_context(
        self, intent: ReceiptIntent, *, lock: bool
    ) -> GovernmentSubsidyReceiptContext: ...

    def load_reversal_context(
        self, intent: ReversalIntent, *, lock: bool
    ) -> GovernmentSubsidyReversalContext: ...

    def load_batch(self, batch_id: int) -> ClaimBatchFacts: ...

    def claim_command(
        self,
        request: GovernmentSubsidyApplyRequest,
        command_fingerprint: PreviewFingerprint,
    ) -> GovernmentSubsidyClaimState: ...

    def find_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredGovernmentSubsidyReceipt | None: ...

    def append_ledger_transaction(
        self,
        request: GovernmentSubsidyApplyRequest,
        candidate: GovernmentSubsidyLedgerCandidate,
    ) -> int: ...

    def append_allocations(
        self,
        transaction_id: int,
        candidate: GovernmentSubsidyLedgerCandidate,
    ) -> tuple[int, ...]: ...

    def update_batch_projection(
        self, command: GovernmentSubsidyProjectionCommand
    ) -> None: ...

    def append_projection_event(
        self,
        request: GovernmentSubsidyApplyRequest,
        candidate: GovernmentSubsidyLedgerCandidate,
        transaction_id: int,
    ) -> int: ...

    def append_outbox(
        self,
        request: GovernmentSubsidyApplyRequest,
        candidate: GovernmentSubsidyLedgerCandidate,
        transaction_id: int,
        projection_event_id: int,
    ) -> None: ...

    def save_receipt(
        self, command: GovernmentSubsidyReceiptPersistenceCommand
    ) -> None: ...


class GovernmentSubsidyWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class GovernmentSubsidyLedgerWorkflow:
    def __init__(
        self,
        repository: GovernmentSubsidyWorkflowRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query_batch(self, batch_id: int) -> ClaimBatchFacts:
        return self._repository.load_batch(batch_id)

    def preview_receipt(
        self, intent: ReceiptIntent
    ) -> GovernmentSubsidyPreview:
        context = self._repository.load_receipt_context(intent, lock=False)
        return _receipt_preview(context, intent)

    def preview_reversal(
        self, intent: ReversalIntent
    ) -> GovernmentSubsidyPreview:
        context = self._repository.load_reversal_context(intent, lock=False)
        return _reversal_preview(context, intent)

    def apply_receipt(
        self, request: GovernmentSubsidyReceiptApplyRequest
    ) -> GovernmentSubsidyCommandReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self.apply_receipt_borrowed(request)
            unit_of_work.commit()
            return receipt

    def apply_receipt_borrowed(
        self, request: GovernmentSubsidyReceiptApplyRequest
    ) -> GovernmentSubsidyCommandReceipt:
        return self._apply_in_current_transaction(request)

    def apply_reversal(
        self, request: GovernmentSubsidyReversalApplyRequest
    ) -> GovernmentSubsidyCommandReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self.apply_reversal_borrowed(request)
            unit_of_work.commit()
            return receipt

    def apply_reversal_borrowed(
        self, request: GovernmentSubsidyReversalApplyRequest
    ) -> GovernmentSubsidyCommandReceipt:
        return self._apply_in_current_transaction(request)

    def _apply_in_current_transaction(
        self, request: GovernmentSubsidyApplyRequest
    ) -> GovernmentSubsidyCommandReceipt:
        command_fingerprint = _command_fingerprint(request)
        replay = self._claim_or_replay(request, command_fingerprint)
        if replay is not None:
            return replay
        preview = self._fresh_preview(request)
        return self._persist(request, preview, command_fingerprint)

    def _claim_or_replay(
        self,
        request: GovernmentSubsidyApplyRequest,
        command_fingerprint: PreviewFingerprint,
    ) -> GovernmentSubsidyCommandReceipt | None:
        state = self._repository.claim_command(request, command_fingerprint)
        if state is GovernmentSubsidyClaimState.MISMATCH:
            raise _workflow_error(
                request,
                ErrorCategory.IDEMPOTENCY_MISMATCH,
                "idempotency_mismatch",
                "Idempotency key was used with a different command.",
            )
        stored = self._repository.find_receipt(
            request.idempotency_key, for_update=True
        )
        return _matched_or_missing(request, command_fingerprint, state, stored)

    def _fresh_preview(
        self, request: GovernmentSubsidyApplyRequest
    ) -> GovernmentSubsidyPreview:
        if isinstance(request, GovernmentSubsidyReceiptApplyRequest):
            context = self._repository.load_receipt_context(
                request.intent, lock=True
            )
            preview = _receipt_preview(context, request.intent)
        else:
            context = self._repository.load_reversal_context(
                request.intent, lock=True
            )
            preview = _reversal_preview(context, request.intent)
        _validate_fresh_preview(request, preview)
        return preview

    def _persist(
        self,
        request: GovernmentSubsidyApplyRequest,
        preview: GovernmentSubsidyPreview,
        command_fingerprint: PreviewFingerprint,
    ) -> GovernmentSubsidyCommandReceipt:
        candidate = preview.candidate
        transaction_id = self._repository.append_ledger_transaction(
            request, candidate
        )
        self._repository.append_allocations(transaction_id, candidate)
        self._repository.update_batch_projection(
            GovernmentSubsidyProjectionCommand(candidate)
        )
        projection_event_id = self._repository.append_projection_event(
            request, candidate, transaction_id
        )
        self._repository.append_outbox(
            request, candidate, transaction_id, projection_event_id
        )
        receipt = _build_receipt(transaction_id, candidate)
        self._repository.save_receipt(
            GovernmentSubsidyReceiptPersistenceCommand(
                request,
                StoredGovernmentSubsidyReceipt(command_fingerprint, receipt),
            )
        )
        return receipt


def _receipt_preview(
    context: GovernmentSubsidyReceiptContext, intent: ReceiptIntent
) -> GovernmentSubsidyPreview:
    candidate = build_receipt_candidate(
        context.bank_fact, context.batches, intent
    )
    return GovernmentSubsidyPreview(candidate, candidate.fingerprint)


def _reversal_preview(
    context: GovernmentSubsidyReversalContext, intent: ReversalIntent
) -> GovernmentSubsidyPreview:
    candidate = build_reversal_candidate(
        context.bank_fact, context.batch, context.source_receipt, intent
    )
    return GovernmentSubsidyPreview(candidate, candidate.fingerprint)


def _validate_fresh_preview(
    request: GovernmentSubsidyApplyRequest,
    preview: GovernmentSubsidyPreview,
) -> None:
    current = preview.candidate.expected_batch_version
    if request.expected_batch_version.value != current:
        raise GovernmentSubsidyWorkflowError(
            TypedError(
                ErrorCategory.CONFLICT,
                "government_subsidy_version_conflict",
                "Government Subsidy batch version changed before Apply.",
                request.correlation_id,
                current_version=ExpectedVersion(current),
            )
        )
    if request.preview_fingerprint != preview.fingerprint:
        raise _workflow_error(
            request,
            ErrorCategory.CONFLICT,
            "stale_preview",
            "Government Subsidy facts changed after Preview.",
        )


def _build_receipt(
    transaction_id: int,
    candidate: GovernmentSubsidyLedgerCandidate,
) -> GovernmentSubsidyCommandReceipt:
    return GovernmentSubsidyCommandReceipt(
        candidate.kind,
        transaction_id,
        candidate.batch_id,
        candidate.resulting_batch_version,
        candidate.bank_fact.bank_fact_identity,
        candidate.amount_ntd.amount,
        len(candidate.allocations),
        candidate.after_status.value,
        candidate.outstanding_ntd.amount,
        candidate.fingerprint,
    )


def _command_fingerprint(
    request: GovernmentSubsidyApplyRequest,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "kind": _request_kind(request).value,
            "intent": request.intent.canonical_payload(),
            "expected_batch_version": request.expected_batch_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
        }
    )


def _request_kind(
    request: GovernmentSubsidyApplyRequest,
) -> GovernmentSubsidyLedgerKind:
    if isinstance(request, GovernmentSubsidyReceiptApplyRequest):
        return GovernmentSubsidyLedgerKind.RECEIPT
    return GovernmentSubsidyLedgerKind.REVERSAL


def _matched_or_missing(
    request: GovernmentSubsidyApplyRequest,
    command_fingerprint: PreviewFingerprint,
    state: GovernmentSubsidyClaimState,
    stored: StoredGovernmentSubsidyReceipt | None,
) -> GovernmentSubsidyCommandReceipt | None:
    if stored is not None:
        return _matched_receipt(request, command_fingerprint, stored)
    if state is GovernmentSubsidyClaimState.MATCHED:
        raise _workflow_error(
            request,
            ErrorCategory.INTERNAL,
            "idempotency_evidence_incomplete",
            "The command claim exists without its receipt.",
        )
    return None


def _matched_receipt(
    request: GovernmentSubsidyApplyRequest,
    command_fingerprint: PreviewFingerprint,
    stored: StoredGovernmentSubsidyReceipt,
) -> GovernmentSubsidyCommandReceipt:
    if stored.command_fingerprint == command_fingerprint:
        return stored.receipt
    raise _workflow_error(
        request,
        ErrorCategory.IDEMPOTENCY_MISMATCH,
        "idempotency_mismatch",
        "Idempotency key was used with a different command.",
    )


def _validate_apply_request(
    request: GovernmentSubsidyApplyRequest,
    intent_type: type[ReceiptIntent] | type[ReversalIntent],
) -> None:
    if not isinstance(request.intent, intent_type):
        raise TypeError("government subsidy intent is invalid")
    require_canonical_text(
        request.reason,
        "government subsidy reason",
        _REASON_MAXIMUM_LENGTH,
    )


def _workflow_error(
    request: GovernmentSubsidyApplyRequest,
    category: ErrorCategory,
    code: str,
    message: str,
) -> GovernmentSubsidyWorkflowError:
    return GovernmentSubsidyWorkflowError(
        TypedError(category, code, message, request.correlation_id)
    )


__all__ = [
    "GovernmentSubsidyApplyRequest",
    "GovernmentSubsidyClaimState",
    "GovernmentSubsidyCommandReceipt",
    "GovernmentSubsidyLedgerWorkflow",
    "GovernmentSubsidyPreview",
    "GovernmentSubsidyProjectionCommand",
    "GovernmentSubsidyReceiptApplyRequest",
    "GovernmentSubsidyReceiptContext",
    "GovernmentSubsidyReceiptPersistenceCommand",
    "GovernmentSubsidyReversalApplyRequest",
    "GovernmentSubsidyReversalContext",
    "GovernmentSubsidyWorkflowError",
    "GovernmentSubsidyWorkflowRepository",
    "StoredGovernmentSubsidyReceipt",
]

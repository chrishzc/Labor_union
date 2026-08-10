"""Record a reviewed refund return without changing the financial ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.client_finance.refund_return_review import (
    RefundReturnReviewCandidate,
    RefundReturnReviewFacts,
    RefundReturnReviewSelection,
    build_refund_return_review_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class RefundReturnReviewPreview:
    candidate: RefundReturnReviewCandidate
    batch_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class RefundReturnReviewApplyRequest:
    selection: RefundReturnReviewSelection
    expected_batch_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class RefundReturnReviewReceipt:
    review_event_identity: str
    row_identity: str
    original_refund_ledger_entry_identity: str
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredRefundReturnReviewReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: RefundReturnReviewReceipt


class RefundReturnReviewRepository(Protocol):
    def load_refund_return_review(
        self,
        selection: RefundReturnReviewSelection,
        *,
        for_update: bool,
    ) -> RefundReturnReviewFacts: ...
    def find_refund_return_review_receipt(
        self,
        key: IdempotencyKey,
    ) -> StoredRefundReturnReviewReceipt | None: ...
    def append_refund_return_review(
        self,
        candidate: RefundReturnReviewCandidate,
        request: RefundReturnReviewApplyRequest,
    ) -> str: ...
    def save_refund_return_review_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredRefundReturnReviewReceipt,
    ) -> None: ...


class RefundReturnReviewWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class RefundReturnReviewWorkflow:
    def __init__(self, repository: RefundReturnReviewRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, selection: RefundReturnReviewSelection, correlation_id: CorrelationId) -> RefundReturnReviewPreview:
        try:
            return _preview(selection, self._repository.load_refund_return_review(selection, for_update=False))
        except ValueError as error:
            raise _domain_error(correlation_id, str(error)) from error

    def apply(self, request: RefundReturnReviewApplyRequest) -> RefundReturnReviewReceipt:
        try:
            return self._apply(request)
        except RefundReturnReviewWorkflowError:
            raise
        except ValueError as error:
            raise _domain_error(request.correlation_id, str(error)) from error
        except Exception as error:
            raise _workflow_error(request.correlation_id, ErrorCategory.INTERNAL, "transaction_failed", str(error) or "Refund return review failed.") from error

    def _apply(self, request):
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._repository.find_refund_return_review_receipt(request.idempotency_key)
            if replay is not None:
                _validate_replay(request, replay, command_fingerprint)
                return replay.receipt
            preview = self._fresh_preview(request)
            event_identity = self._repository.append_refund_return_review(preview.candidate, request)
            receipt = RefundReturnReviewReceipt(event_identity, request.selection.row_identity, request.selection.original_refund_ledger_entry_identity, preview.fingerprint)
            self._repository.save_refund_return_review_receipt(request.idempotency_key, StoredRefundReturnReviewReceipt(command_fingerprint, receipt))
            unit_of_work.commit()
            return receipt

    def _fresh_preview(self, request):
        facts = self._repository.load_refund_return_review(request.selection, for_update=True)
        if facts.batch_version != request.expected_batch_version.value:
            raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_preview", "Refund return review facts changed before Apply.")
        preview = _preview(request.selection, facts)
        if preview.fingerprint != request.preview_fingerprint:
            raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_preview", "Refund return review candidate changed before Apply.")
        return preview


def _preview(selection, facts):
    candidate = build_refund_return_review_candidate(selection, facts)
    fingerprint = fingerprint_payload({"candidate_fingerprint": candidate.fingerprint.value, "batch_version": facts.batch_version})
    return RefundReturnReviewPreview(candidate, facts.batch_version, fingerprint)


def _command_fingerprint(request):
    selection = request.selection
    return fingerprint_payload(
        {
            "row_identity": selection.row_identity,
            "original_refund_ledger_entry_identity": (
                selection.original_refund_ledger_entry_identity
            ),
            "case_no": selection.case_no,
            "reason": selection.reason,
            "evidence": selection.evidence,
            "expected_batch_version": request.expected_batch_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor_id": request.actor.actor_id,
        }
    )


def _validate_replay(request, replay, command_fingerprint):
    if replay.command_fingerprint != command_fingerprint:
        raise _workflow_error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict", "Idempotency key was used by another refund return review.")


def _domain_error(correlation_id, code):
    return _workflow_error(correlation_id, ErrorCategory.DOMAIN_BLOCKED, code, "Refund return review cannot be recorded.", blockers=(code,))


def _workflow_error(correlation_id, category, code, message, *, blockers=()):
    return RefundReturnReviewWorkflowError(TypedError(category, code, message, correlation_id, domain_blockers=tuple(sorted(set(blockers)))))

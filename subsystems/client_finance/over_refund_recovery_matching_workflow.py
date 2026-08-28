"""
File: over_refund_recovery_matching_workflow.py
Description: 協調客戶退款超額追償的 immutable matching。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.client_finance.over_refund_recovery_matching import (
    ClientOverRefundRecoveryMatchingCandidate,
    build_client_over_refund_recovery_matching_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryMatchingSelection:
    case_no: str
    recovery_identity: str
    finance_import_row_identity: str
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.case_no, "case number"),
            (self.recovery_identity, "recovery identity"),
            (self.finance_import_row_identity, "finance import row identity"),
        ):
            require_canonical_text(value, label, 191)
        if self.evidence_reference is not None:
            require_canonical_text(self.evidence_reference, "evidence reference", 500)


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryMatchingFacts:
    recovery_version: int
    account_version: int
    bank_fact_eligible: bool

    def __post_init__(self) -> None:
        require_nonnegative_integer(self.recovery_version, "recovery version")
        require_nonnegative_integer(self.account_version, "account version")


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryMatchingPreview:
    candidate: ClientOverRefundRecoveryMatchingCandidate
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryMatchingApplyRequest:
    selection: ClientOverRefundRecoveryMatchingSelection
    expected_recovery_version: ExpectedVersion
    expected_account_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "reason", 500)
        if self.evidence_reference is not None:
            require_canonical_text(self.evidence_reference, "evidence reference", 500)


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryMatchingReceipt:
    matching_identity: str
    matching_version: int
    recovery_identity: str
    finance_import_row_identity: str
    recovery_version: int
    account_version: int
    preview_fingerprint: PreviewFingerprint
    evidence_reference: str | None = None


@dataclass(frozen=True, slots=True)
class StoredClientOverRefundRecoveryMatchingReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: ClientOverRefundRecoveryMatchingReceipt


class ClientOverRefundRecoveryMatchingRepository(Protocol):
    def load_matching(self, selection: ClientOverRefundRecoveryMatchingSelection, *, for_update: bool) -> ClientOverRefundRecoveryMatchingFacts: ...
    def find_matching_receipt(self, key: IdempotencyKey) -> StoredClientOverRefundRecoveryMatchingReceipt | None: ...
    def persist_matching(self, request: ClientOverRefundRecoveryMatchingApplyRequest, preview: ClientOverRefundRecoveryMatchingPreview, receipt: ClientOverRefundRecoveryMatchingReceipt, command_fingerprint: PreviewFingerprint) -> None: ...


class ClientOverRefundRecoveryMatchingError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class ClientOverRefundRecoveryMatchingWorkflow:
    def __init__(self, repository: ClientOverRefundRecoveryMatchingRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, selection, correlation_id):
        return _preview(self._repository.load_matching(selection, for_update=False), selection, correlation_id)

    def apply(self, request):
        fingerprint = _command_fingerprint(request)
        try:
            with self._unit_of_work_factory() as unit_of_work:
                replay = self._repository.find_matching_receipt(request.idempotency_key)
                if replay is not None:
                    if replay.command_fingerprint == fingerprint:
                        return replay.receipt
                    raise _error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict")
                preview = _fresh_preview(self._repository, request)
                receipt = _receipt(preview, request)
                self._repository.persist_matching(request, preview, receipt, fingerprint)
                unit_of_work.commit()
                return receipt
        except ClientOverRefundRecoveryMatchingError:
            raise
        except Exception as error:
            raise _error(request.correlation_id, ErrorCategory.INTERNAL, "transaction_failed") from error


def _fresh_preview(repository, request):
    if request.evidence_reference != request.selection.evidence_reference:
        raise _error(request.correlation_id, ErrorCategory.CONFLICT, "client_finance_candidate_stale")
    facts = repository.load_matching(request.selection, for_update=True)
    if facts.recovery_version != request.expected_recovery_version.value or facts.account_version != request.expected_account_version.value:
        raise _error(request.correlation_id, ErrorCategory.CONFLICT, "client_finance_candidate_stale")
    preview = _preview(facts, request.selection, request.correlation_id)
    if preview.fingerprint != request.preview_fingerprint:
        raise _error(request.correlation_id, ErrorCategory.CONFLICT, "client_finance_candidate_stale")
    return preview


def _preview(facts, selection, correlation_id):
    try:
        candidate = build_client_over_refund_recovery_matching_candidate(
            case_no=selection.case_no,
            recovery_identity=selection.recovery_identity,
            finance_import_row_identity=selection.finance_import_row_identity,
            recovery_version=facts.recovery_version,
            account_version=facts.account_version,
            bank_fact_eligible=facts.bank_fact_eligible,
        )
    except ValueError as error:
        raise _error(correlation_id, ErrorCategory.DOMAIN_BLOCKED, str(error)) from error
    return ClientOverRefundRecoveryMatchingPreview(
        candidate,
        fingerprint_payload({
            "candidate": candidate.fingerprint.value,
            "evidence_reference": selection.evidence_reference or "",
        }),
    )


def _receipt(preview, request):
    candidate = preview.candidate
    return ClientOverRefundRecoveryMatchingReceipt(
        matching_identity=f"client-recovery-match:{request.idempotency_key.value}",
        matching_version=1,
        recovery_identity=candidate.recovery_identity,
        finance_import_row_identity=candidate.finance_import_row_identity,
        recovery_version=candidate.recovery_version,
        account_version=candidate.account_version,
        preview_fingerprint=preview.fingerprint,
        evidence_reference=request.evidence_reference,
    )


def _command_fingerprint(request):
    return fingerprint_payload({
        "selection": request.selection.__dict__ if hasattr(request.selection, "__dict__") else {
            "case_no": request.selection.case_no, "recovery_identity": request.selection.recovery_identity,
            "finance_import_row_identity": request.selection.finance_import_row_identity,
            "evidence_reference": request.selection.evidence_reference or ""},
        "expected_recovery_version": request.expected_recovery_version.value,
        "expected_account_version": request.expected_account_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor": request.actor.actor_id, "reason": request.reason,
        "evidence_reference": request.evidence_reference or "",
    })


def _error(correlation_id, category, code):
    return ClientOverRefundRecoveryMatchingError(TypedError(category, code, "Client recovery matching cannot be applied.", correlation_id, domain_blockers=(code,) if category is ErrorCategory.DOMAIN_BLOCKED else ()))


__all__ = [name for name in globals() if name.startswith("ClientOverRefundRecovery") or name.startswith("StoredClient")]

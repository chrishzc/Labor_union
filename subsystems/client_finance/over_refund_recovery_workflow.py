"""
File: over_refund_recovery_workflow.py
Description: 協調客戶退款超額追償的 collection 與 authorized adjustment。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol

from domains.client_finance.over_refund_recovery import (
    ClientOverRefundRecovery,
    ClientOverRefundRecoveryAdjustmentCandidate,
    ClientOverRefundRecoveryCandidate,
    ClientRecoveryIncomingBankFact,
    build_client_over_refund_recovery_candidate,
    build_client_over_refund_recovery_adjustment_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_canonical_text


class ClientOverRefundRecoveryAction(StrEnum):
    COLLECT = "collect"
    ADJUST = "adjust"


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoverySelection:
    case_no: str
    recovery_identity: str
    finance_import_row_identity: str | None = None
    action: ClientOverRefundRecoveryAction = ClientOverRefundRecoveryAction.COLLECT
    adjustment_amount: MoneyNTD | None = None
    matching_identity: str | None = None
    matching_version: int | None = None
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.case_no, "case number"),
            (self.recovery_identity, "recovery identity"),
        ):
            require_canonical_text(value, label, 191)
        if self.action is ClientOverRefundRecoveryAction.COLLECT:
            require_canonical_text(
                self.finance_import_row_identity or "",
                "finance import row identity",
                191,
            )
            if self.adjustment_amount is not None:
                raise ValueError("client_over_refund_recovery_action_invalid")
            if self.matching_identity is None or self.matching_version is None:
                raise ValueError("client_over_refund_recovery_matching_required")
            if (self.matching_identity is None) != (self.matching_version is None):
                raise ValueError("client_over_refund_recovery_matching_invalid")
            require_canonical_text(self.matching_identity, "matching identity", 191)
            if not isinstance(self.matching_version, int) or self.matching_version <= 0:
                raise ValueError("client_over_refund_recovery_matching_invalid")
        elif self.action is ClientOverRefundRecoveryAction.ADJUST:
            if (
                self.finance_import_row_identity is not None
                or self.adjustment_amount is None
                or self.matching_identity is not None
                or self.matching_version is not None
            ):
                raise ValueError("client_over_refund_recovery_action_invalid")
        else:
            raise TypeError("client recovery action is invalid")
        if self.evidence_reference is not None:
            require_canonical_text(self.evidence_reference, "evidence reference", 500)


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryFacts:
    recovery: ClientOverRefundRecovery
    bank_fact: ClientRecoveryIncomingBankFact | None
    account_version: int
    adjustment_authorized: bool = False


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryPreview:
    candidate: ClientOverRefundRecoveryCandidate | ClientOverRefundRecoveryAdjustmentCandidate
    account_version: int
    recovery_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ClientOverRefundRecoveryApplyRequest:
    selection: ClientOverRefundRecoverySelection
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
class ClientOverRefundRecoveryReceipt:
    recovery_identity: str
    account_version: int
    recovery_version: int
    remaining_after_ntd: int
    resulting_status: str
    preview_fingerprint: PreviewFingerprint
    evidence_reference: str | None = None


@dataclass(frozen=True, slots=True)
class StoredClientOverRefundRecoveryReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: ClientOverRefundRecoveryReceipt


class ClientOverRefundRecoveryRepository(Protocol):
    def load(self, selection: ClientOverRefundRecoverySelection, *, for_update: bool) -> ClientOverRefundRecoveryFacts: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredClientOverRefundRecoveryReceipt | None: ...
    def persist(self, request: ClientOverRefundRecoveryApplyRequest, preview: ClientOverRefundRecoveryPreview, receipt: ClientOverRefundRecoveryReceipt, command_fingerprint: PreviewFingerprint) -> None: ...


class ClientOverRefundRecoveryError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class ClientOverRefundRecoveryWorkflow:
    def __init__(self, repository: ClientOverRefundRecoveryRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, selection: ClientOverRefundRecoverySelection, correlation_id: CorrelationId) -> ClientOverRefundRecoveryPreview:
        return _build_preview(self._repository.load(selection, for_update=False), selection, correlation_id)

    def apply(self, request: ClientOverRefundRecoveryApplyRequest) -> ClientOverRefundRecoveryReceipt:
        command_fingerprint = _command_fingerprint(request)
        try:
            with self._unit_of_work_factory() as unit_of_work:
                replay = self._find_replay(request, command_fingerprint)
                if replay is not None:
                    return replay
                preview = self._fresh_preview(request)
                receipt = _receipt(preview, request)
                self._repository.persist(request, preview, receipt, command_fingerprint)
                unit_of_work.commit()
                return receipt
        except ClientOverRefundRecoveryError:
            raise
        except Exception as error:
            raise _transaction_error(request, error) from error

    def _find_replay(self, request, command_fingerprint):
        stored = self._repository.find_receipt(request.idempotency_key)
        if stored is None:
            return None
        if stored.command_fingerprint == command_fingerprint:
            return stored.receipt
        raise _error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict")

    def _fresh_preview(self, request):
        if request.evidence_reference != request.selection.evidence_reference:
            raise _error(request.correlation_id, ErrorCategory.CONFLICT, "client_finance_candidate_stale")
        facts = self._repository.load(request.selection, for_update=True)
        if facts.recovery.version != request.expected_recovery_version.value or facts.account_version != request.expected_account_version.value:
            raise _error(request.correlation_id, ErrorCategory.CONFLICT, "client_finance_candidate_stale")
        preview = _build_preview(facts, request.selection, request.correlation_id)
        if preview.fingerprint != request.preview_fingerprint:
            raise _error(request.correlation_id, ErrorCategory.CONFLICT, "client_finance_candidate_stale")
        return preview


def _build_preview(facts, selection, correlation_id):
    try:
        candidate = _candidate(facts, selection)
    except ValueError as error:
        raise _error(correlation_id, _category(str(error)), str(error)) from error
    fingerprint = fingerprint_payload({
        "selection": _selection_payload(selection),
        "account_version": facts.account_version,
        "candidate": candidate.fingerprint.value,
    })
    return ClientOverRefundRecoveryPreview(candidate, facts.account_version, facts.recovery.version, fingerprint)


def _receipt(preview, request):
    candidate = preview.candidate
    return ClientOverRefundRecoveryReceipt(
        candidate.recovery_identity,
        preview.account_version + 1,
        preview.recovery_version + 1,
        candidate.remaining_after.amount,
        candidate.resulting_status.value,
        preview.fingerprint,
        request.evidence_reference,
    )


def _command_fingerprint(request):
    return fingerprint_payload({
        "selection": _selection_payload(request.selection),
        "expected_recovery_version": request.expected_recovery_version.value,
        "expected_account_version": request.expected_account_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor": request.actor.actor_id,
        "reason": request.reason,
        "evidence_reference": request.evidence_reference or "",
    })


def _selection_payload(selection):
    return {
        "case_no": selection.case_no,
        "recovery_identity": selection.recovery_identity,
        "finance_import_row_identity": selection.finance_import_row_identity,
        "action": selection.action.value,
        "adjustment_amount_ntd": None if selection.adjustment_amount is None else selection.adjustment_amount.amount,
        "matching_identity": selection.matching_identity,
        "matching_version": selection.matching_version,
        "evidence_reference": selection.evidence_reference or "",
    }


def _candidate(facts, selection):
    if selection.action is ClientOverRefundRecoveryAction.COLLECT:
        if facts.bank_fact is None:
            raise ValueError("bank_fact_not_eligible")
        return build_client_over_refund_recovery_candidate(
            facts.recovery,
            facts.bank_fact,
        )
    return build_client_over_refund_recovery_adjustment_candidate(
        facts.recovery,
        selection.adjustment_amount,
        adjustment_authorized=facts.adjustment_authorized,
    )


def _category(code):
    if code.endswith("forbidden"):
        return ErrorCategory.FORBIDDEN
    return ErrorCategory.NOT_FOUND if code.endswith("not_found") else ErrorCategory.DOMAIN_BLOCKED


def _error(correlation_id, category, code):
    return ClientOverRefundRecoveryError(TypedError(category, code, "Client over-refund recovery cannot be applied.", correlation_id, domain_blockers=(code,) if category is ErrorCategory.DOMAIN_BLOCKED else ()))


def _transaction_error(request, error):
    del error
    return _error(request.correlation_id, ErrorCategory.INTERNAL, "transaction_failed")


__all__ = [name for name in globals() if name.startswith("ClientOverRefundRecovery") or name.startswith("StoredClient")]

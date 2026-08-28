"""
File: overpayment_recovery.py
Description: 協調 Staff Payables 追償的 evidence-bound Preview／Apply。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol, TypeAlias

from domains.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecovery,
    StaffOverpaymentRecoveryAdjustmentCandidate,
    StaffOverpaymentRecoveryCollectionCandidate,
    StaffRecoveryIncomingBankFact,
    build_staff_overpayment_recovery_adjustment_candidate,
    build_staff_overpayment_recovery_collection_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text


class StaffOverpaymentRecoveryAction(StrEnum):
    COLLECT = "collect"
    ADJUST = "adjust"


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoverySelection:
    recovery_identity: str
    action: StaffOverpaymentRecoveryAction
    finance_import_row_identity: str | None = None
    adjustment_amount: MoneyNTD | None = None
    matching_identity: str | None = None
    matching_version: int | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.recovery_identity, "staff recovery identity", 191)
        if self.action is StaffOverpaymentRecoveryAction.COLLECT:
            require_canonical_text(self.finance_import_row_identity or "", "finance import row identity", 191)
            if self.adjustment_amount is not None:
                raise ValueError("staff_overpayment_recovery_action_invalid")
            if self.matching_identity is None or self.matching_version is None:
                raise ValueError("staff_overpayment_recovery_matching_required")
            if (self.matching_identity is None) != (self.matching_version is None):
                raise ValueError("staff_overpayment_recovery_matching_invalid")
            require_canonical_text(self.matching_identity, "staff matching identity", 191)
            if not isinstance(self.matching_version, int) or self.matching_version <= 0:
                raise ValueError("staff_overpayment_recovery_matching_invalid")
        elif self.action is StaffOverpaymentRecoveryAction.ADJUST:
            if (
                self.finance_import_row_identity is not None
                or self.adjustment_amount is None
                or self.matching_identity is not None
                or self.matching_version is not None
            ):
                raise ValueError("staff_overpayment_recovery_action_invalid")
        else:
            raise TypeError("staff recovery action is invalid")


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryFacts:
    recovery: StaffOverpaymentRecovery
    staff_payables_version: int
    incoming_bank_fact: StaffRecoveryIncomingBankFact | None = None
    adjustment_authorized: bool = False


StaffOverpaymentRecoveryCandidate: TypeAlias = (
    StaffOverpaymentRecoveryCollectionCandidate
    | StaffOverpaymentRecoveryAdjustmentCandidate
)


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryPreview:
    candidate: StaffOverpaymentRecoveryCandidate
    staff_payables_version: int
    recovery_version: int
    fingerprint: PreviewFingerprint
    evidence_reference: str | None = None


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryApplyRequest:
    selection: StaffOverpaymentRecoverySelection
    expected_recovery_version: ExpectedVersion
    expected_staff_payables_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "reason", 500)
        if self.evidence_reference is not None:
            require_canonical_text(self.evidence_reference, "evidence reference", 191)


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryReceipt:
    recovery_identity: str
    recovery_version: int
    staff_payables_version: int
    remaining_after_ntd: int
    resulting_status: str
    preview_fingerprint: PreviewFingerprint
    evidence_reference: str | None = None


@dataclass(frozen=True, slots=True)
class StoredStaffOverpaymentRecoveryReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: StaffOverpaymentRecoveryReceipt


class StaffOverpaymentRecoveryRepository(Protocol):
    def load(self, selection: StaffOverpaymentRecoverySelection, *, for_update: bool) -> StaffOverpaymentRecoveryFacts: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredStaffOverpaymentRecoveryReceipt | None: ...
    def persist(self, request: StaffOverpaymentRecoveryApplyRequest, preview: StaffOverpaymentRecoveryPreview, receipt: StaffOverpaymentRecoveryReceipt, command_fingerprint: PreviewFingerprint) -> None: ...


class StaffOverpaymentRecoveryError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class StaffOverpaymentRecoveryWorkflow:
    def __init__(self, repository: StaffOverpaymentRecoveryRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, selection: StaffOverpaymentRecoverySelection, correlation_id: CorrelationId, evidence_reference: str | None = None) -> StaffOverpaymentRecoveryPreview:
        return _build_preview(self._repository.load(selection, for_update=False), selection, correlation_id, evidence_reference)

    def apply(self, request: StaffOverpaymentRecoveryApplyRequest) -> StaffOverpaymentRecoveryReceipt:
        fingerprint = _command_fingerprint(request)
        try:
            with self._unit_of_work_factory() as unit_of_work:
                replay = self._find_replay(request, fingerprint)
                if replay is not None:
                    return replay
                preview = self._fresh_preview(request)
                receipt = _receipt(preview)
                self._repository.persist(request, preview, receipt, fingerprint)
                unit_of_work.commit()
                return receipt
        except StaffOverpaymentRecoveryError:
            raise
        except Exception as error:
            raise _transaction_error(request, error) from error

    def _find_replay(self, request, fingerprint):
        stored = self._repository.find_receipt(request.idempotency_key)
        if stored is None:
            return None
        if stored.command_fingerprint == fingerprint:
            return stored.receipt
        raise _error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict")

    def _fresh_preview(self, request):
        facts = self._repository.load(request.selection, for_update=True)
        if facts.recovery.version != request.expected_recovery_version.value:
            raise _error(request.correlation_id, ErrorCategory.CONFLICT, "staff_overpayment_recovery_stale")
        if facts.staff_payables_version != request.expected_staff_payables_version.value:
            raise _error(request.correlation_id, ErrorCategory.CONFLICT, "staff_overpayment_recovery_stale")
        preview = _build_preview(facts, request.selection, request.correlation_id, request.evidence_reference)
        if preview.fingerprint != request.preview_fingerprint:
            raise _error(request.correlation_id, ErrorCategory.CONFLICT, "staff_overpayment_recovery_stale")
        return preview


def _build_preview(facts, selection, correlation_id, evidence_reference=None):
    try:
        if evidence_reference is not None:
            require_canonical_text(evidence_reference, "evidence reference", 191)
        candidate = _candidate(facts, selection)
    except ValueError as error:
        raise _error(correlation_id, _category(str(error)), str(error)) from error
    fingerprint = fingerprint_payload({
        "selection": _selection_payload(selection),
        "staff_payables_version": facts.staff_payables_version,
        "candidate": candidate.fingerprint.value,
        "evidence_reference": evidence_reference,
    })
    return StaffOverpaymentRecoveryPreview(
        candidate, facts.staff_payables_version, facts.recovery.version, fingerprint,
        evidence_reference,
    )


def _candidate(facts, selection):
    if selection.action is StaffOverpaymentRecoveryAction.COLLECT:
        if facts.incoming_bank_fact is None:
            raise ValueError("bank_fact_not_eligible")
        return build_staff_overpayment_recovery_collection_candidate(
            facts.recovery, facts.incoming_bank_fact,
        )
    return build_staff_overpayment_recovery_adjustment_candidate(
        facts.recovery,
        selection.adjustment_amount,
        adjustment_authorized=facts.adjustment_authorized,
    )


def _receipt(preview):
    candidate = preview.candidate
    remaining_after = (
        candidate.remaining_after.amount
        if isinstance(candidate, StaffOverpaymentRecoveryCollectionCandidate)
        else 0
    )
    return StaffOverpaymentRecoveryReceipt(
        candidate.recovery_identity,
        preview.recovery_version + 1,
        preview.staff_payables_version + 1,
        remaining_after,
        candidate.resulting_status.value,
        preview.fingerprint,
        preview.evidence_reference,
    )


def _command_fingerprint(request):
    return fingerprint_payload({
        "selection": _selection_payload(request.selection),
        "expected_recovery_version": request.expected_recovery_version.value,
        "expected_staff_payables_version": request.expected_staff_payables_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor": request.actor.actor_id,
        "reason": request.reason,
        "evidence_reference": request.evidence_reference,
    })


def _selection_payload(selection):
    return {
        "recovery_identity": selection.recovery_identity,
        "action": selection.action.value,
        "finance_import_row_identity": selection.finance_import_row_identity,
        "adjustment_amount_ntd": None if selection.adjustment_amount is None else selection.adjustment_amount.amount,
        "matching_identity": selection.matching_identity,
        "matching_version": selection.matching_version,
    }


def _category(code):
    if code.endswith("forbidden"):
        return ErrorCategory.FORBIDDEN
    if code.endswith("not_open"):
        return ErrorCategory.NOT_FOUND
    return ErrorCategory.DOMAIN_BLOCKED


def _error(correlation_id, category, code):
    return StaffOverpaymentRecoveryError(
        TypedError(
            category, code, "Staff overpayment recovery cannot be applied.", correlation_id,
            domain_blockers=(code,) if category is ErrorCategory.DOMAIN_BLOCKED else (),
        )
    )


def _transaction_error(request, error):
    del error
    return _error(request.correlation_id, ErrorCategory.INTERNAL, "transaction_failed")


__all__ = [name for name in globals() if name.startswith("StaffOverpayment") or name.startswith("StoredStaff")]

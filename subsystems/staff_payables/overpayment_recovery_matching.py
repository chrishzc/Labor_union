"""
File: overpayment_recovery_matching.py
Description: 協調 Staff Payables 追償配對的 evidence-bound Preview／Apply。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.staff_payables.overpayment_recovery_matching import (
    StaffOverpaymentRecoveryMatchingCandidate,
    build_staff_overpayment_recovery_matching_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryMatchingSelection:
    recovery_identity: str
    finance_import_row_identity: str
    def __post_init__(self):
        require_canonical_text(self.recovery_identity, "staff recovery identity", 191)
        require_canonical_text(self.finance_import_row_identity, "finance import row identity", 191)


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryMatchingFacts:
    staff_id: int
    recovery_version: int
    staff_payables_version: int
    bank_fact_eligible: bool
    def __post_init__(self):
        if not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("staff_overpayment_recovery_target_ambiguous")
        require_nonnegative_integer(self.recovery_version, "staff recovery version")
        require_nonnegative_integer(self.staff_payables_version, "staff payables version")


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryMatchingPreview:
    candidate: StaffOverpaymentRecoveryMatchingCandidate
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryMatchingApplyRequest:
    selection: StaffOverpaymentRecoveryMatchingSelection
    expected_recovery_version: ExpectedVersion
    expected_staff_payables_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId
    evidence_reference: str | None = None
    def __post_init__(self):
        require_canonical_text(self.reason, "reason", 500)
        if self.evidence_reference is not None:
            require_canonical_text(self.evidence_reference, "evidence reference", 191)


@dataclass(frozen=True, slots=True)
class StaffOverpaymentRecoveryMatchingReceipt:
    matching_identity: str
    matching_version: int
    recovery_identity: str
    staff_id: int
    finance_import_row_identity: str
    recovery_version: int
    staff_payables_version: int
    preview_fingerprint: PreviewFingerprint
    evidence_reference: str | None = None


@dataclass(frozen=True, slots=True)
class StoredStaffOverpaymentRecoveryMatchingReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: StaffOverpaymentRecoveryMatchingReceipt


class StaffOverpaymentRecoveryMatchingRepository(Protocol):
    def load_matching(self, selection, *, for_update: bool) -> StaffOverpaymentRecoveryMatchingFacts: ...
    def find_matching_receipt(self, key: IdempotencyKey) -> StoredStaffOverpaymentRecoveryMatchingReceipt | None: ...
    def persist_matching(self, request, preview, receipt, command_fingerprint) -> None: ...


class StaffOverpaymentRecoveryMatchingError(Exception):
    def __init__(self, error): super().__init__(error.code); self.error = error


class StaffOverpaymentRecoveryMatchingWorkflow:
    def __init__(self, repository: StaffOverpaymentRecoveryMatchingRepository, unit_of_work_factory: Callable[[], UnitOfWork]): self._repository = repository; self._unit_of_work_factory = unit_of_work_factory
    def preview(self, selection, correlation_id, evidence_reference=None): return _preview(self._repository.load_matching(selection, for_update=False), selection, correlation_id, evidence_reference)
    def apply(self, request):
        command_fingerprint = _command_fingerprint(request)
        try:
            with self._unit_of_work_factory() as unit_of_work:
                replay = self._repository.find_matching_receipt(request.idempotency_key)
                if replay is not None:
                    if replay.command_fingerprint == command_fingerprint: return replay.receipt
                    raise _error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict")
                facts = self._repository.load_matching(request.selection, for_update=True)
                if facts.recovery_version != request.expected_recovery_version.value or facts.staff_payables_version != request.expected_staff_payables_version.value:
                    raise _error(request.correlation_id, ErrorCategory.CONFLICT, "staff_overpayment_recovery_stale")
                preview = _preview(facts, request.selection, request.correlation_id, request.evidence_reference)
                if preview.fingerprint != request.preview_fingerprint:
                    raise _error(request.correlation_id, ErrorCategory.CONFLICT, "staff_overpayment_recovery_stale")
                receipt = StaffOverpaymentRecoveryMatchingReceipt(
                    f"staff-recovery-match:{request.idempotency_key.value}", 1,
                    preview.candidate.recovery_identity, preview.candidate.staff_id,
                    preview.candidate.finance_import_row_identity, preview.candidate.recovery_version,
                    preview.candidate.staff_payables_version, preview.fingerprint,
                    request.evidence_reference,
                )
                self._repository.persist_matching(request, preview, receipt, command_fingerprint)
                unit_of_work.commit(); return receipt
        except StaffOverpaymentRecoveryMatchingError: raise
        except Exception as error: raise _error(request.correlation_id, ErrorCategory.INTERNAL, "transaction_failed") from error


def _preview(facts, selection, correlation_id, evidence_reference=None):
    try:
        if evidence_reference is not None:
            require_canonical_text(evidence_reference, "evidence reference", 191)
        candidate = build_staff_overpayment_recovery_matching_candidate(
            recovery_identity=selection.recovery_identity, staff_id=facts.staff_id,
            finance_import_row_identity=selection.finance_import_row_identity,
            recovery_version=facts.recovery_version, staff_payables_version=facts.staff_payables_version,
            bank_fact_eligible=facts.bank_fact_eligible)
    except ValueError as error: raise _error(correlation_id, ErrorCategory.DOMAIN_BLOCKED, str(error)) from error
    fingerprint = fingerprint_payload({
        "candidate": candidate.fingerprint.value,
        "evidence_reference": evidence_reference,
    })
    return StaffOverpaymentRecoveryMatchingPreview(candidate, fingerprint)


def _command_fingerprint(request):
    return fingerprint_payload({"recovery_identity": request.selection.recovery_identity, "finance_import_row_identity": request.selection.finance_import_row_identity, "expected_recovery_version": request.expected_recovery_version.value, "expected_staff_payables_version": request.expected_staff_payables_version.value, "preview_fingerprint": request.preview_fingerprint.value, "actor": request.actor.actor_id, "reason": request.reason, "evidence_reference": request.evidence_reference})


def _error(correlation_id, category, code):
    return StaffOverpaymentRecoveryMatchingError(TypedError(category, code, "Staff recovery matching cannot be applied.", correlation_id, domain_blockers=(code,) if category is ErrorCategory.DOMAIN_BLOCKED else ()))

"""PAYOUT-002 Payroll-owned Query/Preview/Apply workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.payroll.late_obligation import (
    LatePayrollObligationCandidate,
    LatePayrollObligationFacts,
    LatePayrollObligationIntent,
    build_late_payroll_obligation_candidate,
    late_obligation_completion_matches,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text


@dataclass(frozen=True, slots=True)
class LatePayrollObligationPreview:
    candidate: LatePayrollObligationCandidate
    payroll_version: int
    obligation_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class LatePayrollObligationApplyRequest:
    intent: LatePayrollObligationIntent
    expected_payroll_version: ExpectedVersion
    expected_obligation_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "reason", 500)


@dataclass(frozen=True, slots=True)
class LatePayrollObligationReceipt:
    case_no: str
    obligation_identity: str
    source_event_identity: str
    disposition: str
    delta_amount_ntd: int
    corrected_amount_ntd: int
    recovery_amount_ntd: int
    payroll_version: int
    obligation_version: int
    correction_identity: str
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredLatePayrollObligationReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: LatePayrollObligationReceipt


class LatePayrollObligationRepository(Protocol):
    def load(self, intent: LatePayrollObligationIntent, *, for_update: bool) -> LatePayrollObligationFacts: ...

    def find_receipt(self, key: IdempotencyKey) -> StoredLatePayrollObligationReceipt | None: ...

    def persist_payroll_disposition(
        self,
        request: LatePayrollObligationApplyRequest,
        preview: LatePayrollObligationPreview,
        receipt: LatePayrollObligationReceipt,
        command_fingerprint: PreviewFingerprint,
    ) -> None: ...

    # Compatibility spelling for an older local adapter.  New composition
    # must implement persist_payroll_disposition so every branch, including
    # zero delta, has one immutable Payroll owner contract.
    def persist_late_obligation(
        self,
        request: LatePayrollObligationApplyRequest,
        preview: LatePayrollObligationPreview,
        receipt: LatePayrollObligationReceipt,
        command_fingerprint: PreviewFingerprint,
    ) -> None: ...

    def readback_late_obligation(self, intent: LatePayrollObligationIntent) -> LatePayrollObligationFacts: ...


class StaffOverpaymentRecoveryPort(Protocol):
    """Staff Payables handoff; it does not alter Payroll obligation facts."""

    def create_from_payroll_correction(
        self,
        *,
        candidate: LatePayrollObligationCandidate,
        request: LatePayrollObligationApplyRequest,
    ) -> None: ...


class LatePayrollObligationError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class LatePayrollObligationWorkflow:
    def __init__(
        self,
        repository: LatePayrollObligationRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
        staff_overpayment_recovery: StaffOverpaymentRecoveryPort | None = None,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._staff_overpayment_recovery = staff_overpayment_recovery

    def preview(
        self,
        intent: LatePayrollObligationIntent,
        correlation_id: CorrelationId,
    ) -> LatePayrollObligationPreview:
        try:
            return _build_preview(self._repository.load(intent, for_update=False), intent)
        except (TypeError, ValueError) as error:
            raise _validation_error(error, correlation_id) from error

    def apply(self, request: LatePayrollObligationApplyRequest) -> LatePayrollObligationReceipt:
        fingerprint = _command_fingerprint(request)
        stored = self._repository.find_receipt(request.idempotency_key)
        if stored is not None:
            if stored.command_fingerprint == fingerprint:
                return stored.receipt
            raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict")
        try:
            with self._unit_of_work_factory() as unit_of_work:
                preview = self._fresh_preview(request)
                if preview.candidate.requires_staff_overpayment_recovery and self._staff_overpayment_recovery is None:
                    raise _error(
                        request,
                        ErrorCategory.UNAVAILABLE,
                        "staff_overpayment_recovery_unavailable",
                    )
                receipt = _receipt(preview)
                if preview.candidate.requires_staff_overpayment_recovery:
                    self._staff_overpayment_recovery.create_from_payroll_correction(
                        candidate=preview.candidate, request=request
                    )
                persist = getattr(self._repository, "persist_payroll_disposition", None)
                if persist is None:
                    persist = self._repository.persist_late_obligation
                persist(request, preview, receipt, fingerprint)
                unit_of_work.commit()
            try:
                readback = self._repository.readback_late_obligation(request.intent)
            except Exception as error:
                raise _error(
                    request,
                    ErrorCategory.UNAVAILABLE,
                    "payout002_readback_unavailable",
                ) from error
            if not late_obligation_completion_matches(preview.candidate, readback):
                raise _error(request, ErrorCategory.CONFLICT, "payout002_readback_inconsistent")
            return receipt
        except LatePayrollObligationError:
            raise
        except (TypeError, ValueError) as error:
            raise _validation_error(error, request.correlation_id) from error
        except Exception as error:
            boundary_code = str(error)
            if boundary_code.startswith("BOUNDARY_REQUIRED_"):
                raise _error(request, ErrorCategory.UNAVAILABLE, boundary_code) from error
            raise _error(request, ErrorCategory.INTERNAL, "transaction_failed") from error

    def _fresh_preview(self, request: LatePayrollObligationApplyRequest) -> LatePayrollObligationPreview:
        facts = self._repository.load(request.intent, for_update=True)
        if facts.payroll_version != request.expected_payroll_version.value:
            raise _error(request, ErrorCategory.CONFLICT, "payout002_payroll_stale", facts.payroll_version)
        if facts.obligation_version != request.expected_obligation_version.value:
            raise _error(request, ErrorCategory.CONFLICT, "payout002_obligation_stale", facts.obligation_version)
        preview = _build_preview(facts, request.intent)
        if preview.fingerprint != request.preview_fingerprint:
            raise _error(request, ErrorCategory.CONFLICT, "payout002_preview_stale", facts.payroll_version)
        return preview


def _build_preview(facts: LatePayrollObligationFacts, intent: LatePayrollObligationIntent) -> LatePayrollObligationPreview:
    candidate = build_late_payroll_obligation_candidate(facts, intent)
    fingerprint = fingerprint_payload({
        "candidate": candidate.fingerprint.value,
        "payroll_version": facts.payroll_version,
        "obligation_version": facts.obligation_version,
    })
    return LatePayrollObligationPreview(candidate, facts.payroll_version, facts.obligation_version, fingerprint)


def _receipt(preview: LatePayrollObligationPreview) -> LatePayrollObligationReceipt:
    candidate = preview.candidate
    return LatePayrollObligationReceipt(
        candidate.case_no,
        candidate.obligation_identity,
        candidate.source_event_identity,
        candidate.disposition.value,
        candidate.delta_amount.amount,
        candidate.corrected_amount.amount,
        candidate.recovery_amount.amount,
        preview.payroll_version + 1,
        preview.obligation_version + 1,
        candidate.correction_identity,
        preview.fingerprint,
    )


def _command_fingerprint(request: LatePayrollObligationApplyRequest) -> PreviewFingerprint:
    return fingerprint_payload({
        "intent": {
            "case_no": request.intent.case_no,
            "obligation_identity": request.intent.obligation_identity,
            "source_event_identity": request.intent.source_event_identity,
            "corrected_amount_ntd": request.intent.corrected_amount.amount,
        },
        "expected_payroll_version": request.expected_payroll_version.value,
        "expected_obligation_version": request.expected_obligation_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor": request.actor.actor_id,
        "reason": request.reason,
    })


def _validation_error(error, correlation_id):
    return LatePayrollObligationError(TypedError(
        ErrorCategory.VALIDATION,
        str(error) or "payout002_invalid_facts",
        "PAYOUT-002 source or correction facts are invalid.",
        correlation_id,
    ))


def _error(request, category, code, current_version=None):
    return LatePayrollObligationError(TypedError(
        category,
        code,
        "PAYOUT-002 Payroll correction cannot be applied.",
        request.correlation_id,
        current_version=None if current_version is None else ExpectedVersion(current_version),
    ))


# Explicit aliases keep the PAYOUT-002 name discoverable to owner callers while
# retaining the compact module vocabulary used by the other Payroll workflows.
PayrollLateObligationWorkflow = LatePayrollObligationWorkflow
PayrollLateObligationApplyRequest = LatePayrollObligationApplyRequest
PayrollLateObligationPreview = LatePayrollObligationPreview
PayrollLateObligationReceipt = LatePayrollObligationReceipt


__all__ = [
    "LatePayrollObligationApplyRequest",
    "LatePayrollObligationError",
    "LatePayrollObligationPreview",
    "LatePayrollObligationReceipt",
    "LatePayrollObligationRepository",
    "LatePayrollObligationWorkflow",
    "PayrollLateObligationApplyRequest",
    "PayrollLateObligationPreview",
    "PayrollLateObligationReceipt",
    "PayrollLateObligationWorkflow",
    "StaffOverpaymentRecoveryPort",
    "StoredLatePayrollObligationReceipt",
]

"""Atomic Payroll adjustment preview, replay, and persistence orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.payroll.adjustment import (
    PayrollAdjustmentCandidate,
    PayrollAdjustmentFacts,
    PayrollAdjustmentIntent,
    build_payroll_adjustment_candidate,
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


@dataclass(frozen=True, slots=True)
class PayrollAdjustmentPreview:
    payroll_version: int
    candidate: PayrollAdjustmentCandidate
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class PayrollAdjustmentApplyRequest:
    intent: PayrollAdjustmentIntent
    expected_payroll_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "reason", 500)


@dataclass(frozen=True, slots=True)
class PayrollAdjustmentReceipt:
    case_no: str
    payroll_version: int
    adjustment_identity: str
    allocation_count: int
    amount_ntd: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredPayrollAdjustmentReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: PayrollAdjustmentReceipt


class PayrollAdjustmentError(Exception):
    def __init__(self, error: TypedError) -> None:
        self.error = error
        super().__init__(error.code)


class PayrollAdjustmentRepository(Protocol):
    def load(
        self,
        case_no: str,
        *,
        for_update: bool,
    ) -> PayrollAdjustmentFacts: ...

    def find_receipt(
        self,
        key: IdempotencyKey,
    ) -> StoredPayrollAdjustmentReceipt | None: ...

    def persist(
        self,
        request: PayrollAdjustmentApplyRequest,
        preview: PayrollAdjustmentPreview,
        command_fingerprint: PreviewFingerprint,
        receipt: PayrollAdjustmentReceipt,
    ) -> None: ...

    def query_case_payroll(self, case_no: str): ...

    def query_staff_obligations(self, staff_id: int): ...


class PayrollAdjustmentWorkflow:
    def __init__(
        self,
        repository: PayrollAdjustmentRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(
        self,
        intent: PayrollAdjustmentIntent,
        correlation_id: CorrelationId,
    ) -> PayrollAdjustmentPreview:
        try:
            facts = self._repository.load(intent.case_no, for_update=False)
            return _build_preview(facts, intent)
        except (TypeError, ValueError) as error:
            raise _validation_error(error, correlation_id) from error

    def apply(
        self,
        request: PayrollAdjustmentApplyRequest,
    ) -> PayrollAdjustmentReceipt:
        command_fingerprint = _command_fingerprint(request)
        replay = self._find_replay(request, command_fingerprint)
        if replay is not None:
            return replay
        with self._unit_of_work_factory() as unit_of_work:
            preview = self._fresh_preview(request)
            receipt = _build_receipt(preview)
            self._repository.persist(
                request,
                preview,
                command_fingerprint,
                receipt,
            )
            unit_of_work.commit()
        return receipt

    def _find_replay(
        self,
        request: PayrollAdjustmentApplyRequest,
        command_fingerprint: PreviewFingerprint,
    ) -> PayrollAdjustmentReceipt | None:
        stored = self._repository.find_receipt(request.idempotency_key)
        if stored is None:
            return None
        if stored.command_fingerprint == command_fingerprint:
            return stored.receipt
        raise _workflow_error(
            request,
            ErrorCategory.IDEMPOTENCY_MISMATCH,
            "idempotency_conflict",
            "Idempotency key belongs to another Payroll adjustment.",
        )

    def _fresh_preview(
        self,
        request: PayrollAdjustmentApplyRequest,
    ) -> PayrollAdjustmentPreview:
        try:
            facts = self._repository.load(
                request.intent.case_no,
                for_update=True,
            )
            _require_current_version(facts, request)
            preview = _build_preview(facts, request.intent)
            _require_current_fingerprint(preview, request)
            return preview
        except PayrollAdjustmentError:
            raise
        except (TypeError, ValueError) as error:
            raise _validation_error(error, request.correlation_id) from error


def _build_preview(
    facts: PayrollAdjustmentFacts,
    intent: PayrollAdjustmentIntent,
) -> PayrollAdjustmentPreview:
    candidate = build_payroll_adjustment_candidate(facts, intent)
    fingerprint = fingerprint_payload(
        {
            "payroll_version": facts.payroll_version,
            "candidate_fingerprint": candidate.fingerprint.value,
        }
    )
    return PayrollAdjustmentPreview(facts.payroll_version, candidate, fingerprint)


def _build_receipt(preview: PayrollAdjustmentPreview) -> PayrollAdjustmentReceipt:
    candidate = preview.candidate
    return PayrollAdjustmentReceipt(
        candidate.case_no,
        preview.payroll_version + 1,
        candidate.adjustment_identity,
        len(candidate.allocations),
        candidate.amount.amount,
        preview.fingerprint,
    )


def _command_fingerprint(
    request: PayrollAdjustmentApplyRequest,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "case_no": request.intent.case_no,
            "source_event_identity": request.intent.source_event_identity,
            "allocations": tuple(
                {
                    "assignment_id": item.assignment_id,
                    "amount_ntd": item.amount.amount,
                }
                for item in request.intent.allocations
            ),
            "expected_payroll_version": request.expected_payroll_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor_id": request.actor.actor_id,
            "reason": request.reason,
        }
    )


def _require_current_version(
    facts: PayrollAdjustmentFacts,
    request: PayrollAdjustmentApplyRequest,
) -> None:
    if facts.payroll_version == request.expected_payroll_version.value:
        return
    raise _workflow_error(
        request,
        ErrorCategory.CONFLICT,
        "payroll_candidate_stale",
        "Payroll version changed after Preview.",
        current_version=facts.payroll_version,
    )


def _require_current_fingerprint(
    preview: PayrollAdjustmentPreview,
    request: PayrollAdjustmentApplyRequest,
) -> None:
    if preview.fingerprint == request.preview_fingerprint:
        return
    raise _workflow_error(
        request,
        ErrorCategory.CONFLICT,
        "payroll_candidate_stale",
        "Payroll root facts changed after Preview.",
        current_version=preview.payroll_version,
    )


def _validation_error(
    error: TypeError | ValueError,
    correlation_id: CorrelationId,
) -> PayrollAdjustmentError:
    code = str(error) or "invalid_payroll_facts"
    return PayrollAdjustmentError(
        TypedError(
            ErrorCategory.VALIDATION,
            code,
            "Payroll adjustment root facts or intent are invalid.",
            correlation_id,
        )
    )


def _workflow_error(
    request: PayrollAdjustmentApplyRequest,
    category: ErrorCategory,
    code: str,
    message: str,
    *,
    current_version: int | None = None,
) -> PayrollAdjustmentError:
    version = (
        None
        if current_version is None
        else ExpectedVersion(current_version)
    )
    return PayrollAdjustmentError(
        TypedError(category, code, message, request.correlation_id, current_version=version)
    )


__all__ = [
    "PayrollAdjustmentApplyRequest",
    "PayrollAdjustmentError",
    "PayrollAdjustmentPreview",
    "PayrollAdjustmentReceipt",
    "PayrollAdjustmentWorkflow",
    "StoredPayrollAdjustmentReceipt",
]

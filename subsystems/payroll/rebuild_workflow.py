"""
File: rebuild_workflow.py
Description: 以正式服務、費率、到期日與既有付款歷史重建 Payroll obligations。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Callable, Protocol

from domains.payroll.calculation import (
    AssignmentRateSnapshot,
    CasePayrollCandidate,
    OfficialAssignmentServiceFacts,
    PayrollAdjustment,
    PayrollTerms,
    build_case_payroll_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191


class StaffObligationActionKind(StrEnum):
    CREATE = "create"
    REPLACE_UNPAID = "replace_unpaid"
    APPEND_FROZEN_DELTA = "append_frozen_delta"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class ExistingStaffObligation:
    assignment_identity: str
    obligation_identity: str
    amount_due: MoneyNTD
    payout_history_exists: bool
    due_date: date | None

    def __post_init__(self) -> None:
        require_canonical_text(self.assignment_identity, "assignment identity", _IDENTITY_MAXIMUM_LENGTH)
        require_canonical_text(self.obligation_identity, "obligation identity", _IDENTITY_MAXIMUM_LENGTH)
        if not isinstance(self.amount_due, MoneyNTD):
            raise TypeError("staff obligation amount must be MoneyNTD")
        require_nonnegative_integer(self.amount_due.amount, "staff obligation amount")
        if not isinstance(self.payout_history_exists, bool):
            raise TypeError("payout history flag must be bool")
        if self.due_date is not None and not isinstance(self.due_date, date):
            raise TypeError("staff obligation due date must be a date")


@dataclass(frozen=True, slots=True)
class PayrollRebuildFacts:
    case_no: str
    payroll_version: int
    service_facts: tuple[OfficialAssignmentServiceFacts, ...]
    rate_snapshots: tuple[AssignmentRateSnapshot, ...]
    terms: PayrollTerms
    adjustments: tuple[PayrollAdjustment, ...]
    existing_obligations: tuple[ExistingStaffObligation, ...]
    staff_payment_due_date: date | None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _IDENTITY_MAXIMUM_LENGTH)
        require_nonnegative_integer(self.payroll_version, "payroll version")
        if self.staff_payment_due_date is not None and not isinstance(
            self.staff_payment_due_date, date
        ):
            raise TypeError("staff payment due date must be a date")


@dataclass(frozen=True, slots=True)
class StaffObligationAction:
    assignment_identity: str
    obligation_identity: str
    action: StaffObligationActionKind
    before_amount: MoneyNTD
    after_amount: MoneyNTD
    delta_amount: MoneyNTD
    due_date: date | None


@dataclass(frozen=True, slots=True)
class PayrollRebuildPreview:
    payroll: CasePayrollCandidate
    actions: tuple[StaffObligationAction, ...]
    payroll_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class PayrollRebuildRequest:
    case_no: str
    expected_payroll_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.reason, "rebuild reason", 500)


@dataclass(frozen=True, slots=True)
class PayrollRebuildReceipt:
    case_no: str
    payroll_version: int
    action_count: int
    total_payable: MoneyNTD
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredPayrollReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: PayrollRebuildReceipt


@dataclass(frozen=True, slots=True)
class PayrollRebuildPersistence:
    request: PayrollRebuildRequest
    preview: PayrollRebuildPreview
    command_fingerprint: PreviewFingerprint
    receipt: PayrollRebuildReceipt


class PayrollRebuildRepository(Protocol):
    def load(self, case_no: str, *, for_update: bool) -> PayrollRebuildFacts: ...

    def find_receipt(self, key: IdempotencyKey) -> StoredPayrollReceipt | None: ...

    def persist_rebuild(self, persistence: PayrollRebuildPersistence) -> None: ...


class PayrollRebuildError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class PayrollRebuildWorkflow:
    def __init__(
        self,
        repository: PayrollRebuildRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, case_no: str) -> PayrollRebuildPreview:
        return _build_preview(self._repository.load(case_no, for_update=False))

    def apply(self, request: PayrollRebuildRequest) -> PayrollRebuildReceipt:
        try:
            return self._apply_transaction(request)
        except PayrollRebuildError:
            raise
        except (TypeError, ValueError) as error:
            raise _request_validation_error(request, error) from error

    def _apply_transaction(self, request):
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._find_replay(request, command_fingerprint)
            if replay:
                unit_of_work.commit()
                return replay
            preview = self._fresh_preview(request)
            receipt = _receipt(request, preview)
            self._persist(request, preview, command_fingerprint, receipt)
            unit_of_work.commit()
            return receipt

    def _find_replay(self, request, command_fingerprint):
        stored = self._repository.find_receipt(request.idempotency_key)
        if stored is None:
            return None
        if stored.command_fingerprint == command_fingerprint:
            return stored.receipt
        raise _error(
            request,
            ErrorCategory.IDEMPOTENCY_MISMATCH,
            "idempotency_conflict",
            "Idempotency key was used by another Payroll command.",
        )

    def _fresh_preview(self, request):
        facts = self._repository.load(request.case_no, for_update=True)
        if facts.payroll_version != request.expected_payroll_version.value:
            raise _error(request, ErrorCategory.CONFLICT, "payroll_candidate_stale", "Payroll version changed before Apply.", current_version=facts.payroll_version)
        preview = _build_preview(facts)
        if preview.fingerprint != request.preview_fingerprint:
            raise _error(request, ErrorCategory.CONFLICT, "payroll_candidate_stale", "Payroll root facts changed after Preview.", current_version=facts.payroll_version)
        return preview

    def _persist(self, request, preview, command_fingerprint, receipt) -> None:
        self._repository.persist_rebuild(PayrollRebuildPersistence(request, preview, command_fingerprint, receipt))


def _build_preview(facts: PayrollRebuildFacts) -> PayrollRebuildPreview:
    payroll = build_case_payroll_candidate(facts.service_facts, facts.rate_snapshots, facts.terms, facts.adjustments)
    return _preview_result(
        facts,
        payroll,
        _build_actions(
            payroll,
            facts.existing_obligations,
            facts.staff_payment_due_date,
        ),
    )


def _preview_result(facts, payroll, actions) -> PayrollRebuildPreview:
    return PayrollRebuildPreview(
        payroll,
        actions,
        facts.payroll_version,
        fingerprint_payload({
            "case_no": facts.case_no,
            "payroll_version": facts.payroll_version,
            "payroll_fingerprint": payroll.fingerprint.value,
            "actions": tuple(_action_payload(item) for item in actions),
        }),
    )


def _build_actions(payroll, existing_obligations, staff_payment_due_date):
    existing = {item.assignment_identity: item for item in existing_obligations}
    if len(existing) != len(existing_obligations):
        raise ValueError("invalid_payroll_facts")
    candidate_actions = tuple(
        _obligation_action(
            item,
            existing.get(item.assignment_identity),
            staff_payment_due_date,
        )
        for item in payroll.assignments
    )
    candidate_identities = {item.assignment_identity for item in payroll.assignments}
    removed_actions = tuple(_removed_obligation_action(item) for identity, item in sorted(existing.items()) if identity not in candidate_identities)
    return candidate_actions + removed_actions


def _obligation_action(candidate, existing, staff_payment_due_date):
    if existing is None:
        return _new_obligation_action(candidate, staff_payment_due_date)
    delta = candidate.total_payable - existing.amount_due
    due_date = existing.due_date or staff_payment_due_date
    return StaffObligationAction(
        candidate.assignment_identity,
        existing.obligation_identity,
        _existing_action_kind(existing, delta, due_date),
        existing.amount_due,
        candidate.total_payable,
        delta,
        due_date,
    )


def _new_obligation_action(candidate, due_date):
    zero = MoneyNTD(0)
    return StaffObligationAction(candidate.assignment_identity, f"staff-obligation:{candidate.assignment_identity}", StaffObligationActionKind.CREATE, zero, candidate.total_payable, candidate.total_payable, due_date)


def _removed_obligation_action(existing):
    zero = MoneyNTD(0)
    delta = zero - existing.amount_due
    return StaffObligationAction(existing.assignment_identity, existing.obligation_identity, _existing_action_kind(existing, delta, existing.due_date), existing.amount_due, zero, delta, existing.due_date)


def _existing_action_kind(existing, delta, due_date):
    if delta.is_zero:
        if existing.due_date is None and due_date is not None and not existing.payout_history_exists:
            return StaffObligationActionKind.REPLACE_UNPAID
        return StaffObligationActionKind.UNCHANGED
    if existing.payout_history_exists:
        return StaffObligationActionKind.APPEND_FROZEN_DELTA
    return StaffObligationActionKind.REPLACE_UNPAID


def _action_payload(action) -> dict[str, object]:
    return {
        "assignment_identity": action.assignment_identity,
        "obligation_identity": action.obligation_identity,
        "action": action.action.value,
        "before_amount_ntd": action.before_amount.amount,
        "after_amount_ntd": action.after_amount.amount,
        "delta_amount_ntd": action.delta_amount.amount,
        "due_date": action.due_date.isoformat() if action.due_date else None,
    }


def _command_fingerprint(request) -> PreviewFingerprint:
    return fingerprint_payload({
        "case_no": request.case_no,
        "expected_payroll_version": request.expected_payroll_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor_id": request.actor.actor_id,
        "reason": request.reason,
    })


def _receipt(request, preview) -> PayrollRebuildReceipt:
    return PayrollRebuildReceipt(
        request.case_no,
        preview.payroll_version + 1,
        sum(item.action is not StaffObligationActionKind.UNCHANGED for item in preview.actions),
        preview.payroll.total_payable,
        preview.fingerprint,
    )


def _error(request, category, code, message, *, current_version=None) -> PayrollRebuildError:
    return PayrollRebuildError(TypedError(category, code, message, request.correlation_id, current_version=_expected_version(current_version)))


def _expected_version(current_version):
    return None if current_version is None else ExpectedVersion(current_version)


def _request_validation_error(request, error):
    code = str(error) or "invalid_payroll_facts"
    category = ErrorCategory.CONFLICT if code == "payroll_candidate_stale" else ErrorCategory.DOMAIN_BLOCKED if code == "staff_obligation_frozen" else ErrorCategory.VALIDATION
    return _error(request, category, code, "Payroll rebuild root facts or persistence state are invalid.")


__all__ = [
    "ExistingStaffObligation", "PayrollRebuildError", "PayrollRebuildFacts",
    "PayrollRebuildPersistence", "PayrollRebuildPreview", "PayrollRebuildReceipt",
    "PayrollRebuildRequest", "PayrollRebuildWorkflow", "StaffObligationAction",
    "StaffObligationActionKind", "StoredPayrollReceipt",
]

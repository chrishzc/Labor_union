"""Controlled Orders reopening transaction without a preserved-bytecode bridge."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol

from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.reopen import ReopenCandidate, ReopenCandidateError, ReopenFinancialEventFact, ReopenOrderFacts, build_reopen_candidate
from shared_kernel.clock import BusinessClock
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.terms_workflow import CommandClaimState


@dataclass(frozen=True, slots=True)
class ReopenWorkflowFacts:
    order: ReopenOrderFacts
    financial_events: tuple[ReopenFinancialEventFact, ...]
    client_finance_version: int
    payroll_version: int


@dataclass(frozen=True, slots=True)
class OrderReopenPreview:
    candidate: ReopenCandidate
    client_finance_version: int
    payroll_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class OrderReopenApplyRequest:
    case_no: str
    expected_order_version: ExpectedVersion
    expected_client_finance_version: ExpectedVersion
    expected_payroll_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class OrderReopenReceipt:
    case_no: str
    order_version: int
    lifecycle_status: OrderLifecycleStatus
    cancellation_event_id: int
    requires_fresh_scheduling_preview: bool
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredReopenReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: OrderReopenReceipt


@dataclass(frozen=True, slots=True)
class ReopenOrderPersistenceCommand:
    case_no: str
    expected_order_version: int
    resulting_order_version: int
    lifecycle_status: OrderLifecycleStatus


@dataclass(frozen=True, slots=True)
class ReopenReceiptPersistenceCommand:
    key: IdempotencyKey
    stored_receipt: StoredReopenReceipt
    reopen_event_id: int
    cancellation_control_event_id: int
    lifecycle_event_id: int
    correlation_id: CorrelationId


class ReopenWorkflowRepository(Protocol):
    def load_for_preview(self, case_no: str) -> ReopenWorkflowFacts: ...
    def load_for_apply(self, case_no: str) -> ReopenWorkflowFacts: ...
    def find_receipt(self, key: IdempotencyKey, *, for_update: bool) -> StoredReopenReceipt | None: ...
    def claim_command(self, request: OrderReopenApplyRequest, command_fingerprint: PreviewFingerprint) -> CommandClaimState: ...
    def append_reopen_event(self, request: OrderReopenApplyRequest, preview: OrderReopenPreview) -> int: ...
    def clear_cancellation_control(self, request: OrderReopenApplyRequest, reopen_event_id: int) -> int: ...
    def append_reopen_lifecycle(self, request: OrderReopenApplyRequest, preview: OrderReopenPreview, cancellation_control_event_id: int, business_date: date) -> int: ...
    def update_reopened_order(self, command: ReopenOrderPersistenceCommand) -> None: ...
    def save_receipt(self, command: ReopenReceiptPersistenceCommand) -> None: ...


class ReopenWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class OrderReopenWorkflow:
    def __init__(self, repository: ReopenWorkflowRepository, unit_of_work_factory: Callable[[], object], clock: BusinessClock) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def preview(self, case_no: str) -> OrderReopenPreview:
        return _build_preview(self._repository.load_for_preview(case_no))

    def apply(self, request: OrderReopenApplyRequest) -> OrderReopenReceipt:
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            claim = self._repository.claim_command(request, command_fingerprint)
            _raise_if_claim_mismatched(request, claim)
            replay = self._find_replay(request, command_fingerprint)
            if replay is not None:
                return replay
            _raise_if_claim_incomplete(request, claim)
            preview = self._fresh_preview(request)
            receipt = _build_receipt(preview)
            self._persist(request, preview, command_fingerprint, receipt)
            unit_of_work.commit()
            return receipt

    def _find_replay(self, request: OrderReopenApplyRequest, command_fingerprint: PreviewFingerprint) -> OrderReopenReceipt | None:
        stored = self._repository.find_receipt(request.idempotency_key, for_update=True)
        if stored is None:
            return None
        if stored.command_fingerprint == command_fingerprint:
            return stored.receipt
        raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was used by a different reopen command.")

    def _fresh_preview(self, request: OrderReopenApplyRequest) -> OrderReopenPreview:
        facts = self._repository.load_for_apply(request.case_no)
        _validate_expected_versions(request, facts)
        try:
            preview = _build_preview(facts)
        except ReopenCandidateError as error:
            raise _candidate_workflow_error(request, error) from error
        if preview.fingerprint != request.preview_fingerprint:
            raise _workflow_error(request, ErrorCategory.CONFLICT, "stale_preview", "The reopen facts changed after Preview.")
        return preview

    def _persist(self, request: OrderReopenApplyRequest, preview: OrderReopenPreview, command_fingerprint: PreviewFingerprint, receipt: OrderReopenReceipt) -> None:
        reopen_event_id = self._repository.append_reopen_event(request, preview)
        control_event_id = self._repository.clear_cancellation_control(request, reopen_event_id)
        lifecycle_event_id = self._repository.append_reopen_lifecycle(request, preview, control_event_id, self._clock.today())
        self._repository.update_reopened_order(ReopenOrderPersistenceCommand(request.case_no, preview.candidate.expected_order_version, receipt.order_version, receipt.lifecycle_status))
        self._repository.save_receipt(ReopenReceiptPersistenceCommand(request.idempotency_key, StoredReopenReceipt(command_fingerprint, receipt), reopen_event_id, control_event_id, lifecycle_event_id, request.correlation_id))


def _build_preview(facts: ReopenWorkflowFacts) -> OrderReopenPreview:
    candidate = build_reopen_candidate(facts.order, facts.financial_events)
    return OrderReopenPreview(candidate, facts.client_finance_version, facts.payroll_version, fingerprint_payload({"candidate": candidate.fingerprint.value, "client_finance_version": facts.client_finance_version, "payroll_version": facts.payroll_version}))


def _build_receipt(preview: OrderReopenPreview) -> OrderReopenReceipt:
    candidate = preview.candidate
    return OrderReopenReceipt(candidate.case_no, candidate.expected_order_version + 1, candidate.after_status, candidate.cancellation_event_id, candidate.requires_fresh_scheduling_preview, preview.fingerprint)


def _validate_expected_versions(request: OrderReopenApplyRequest, facts: ReopenWorkflowFacts) -> None:
    comparisons = ((request.expected_order_version.value, facts.order.order_version, "order"), (request.expected_client_finance_version.value, facts.client_finance_version, "client_finance"), (request.expected_payroll_version.value, facts.payroll_version, "payroll"))
    for expected, current, domain in comparisons:
        if expected != current:
            code = "client_finance_candidate_stale" if domain == "client_finance" else f"{domain}_version_conflict"
            raise _workflow_error(request, ErrorCategory.CONFLICT, code, f"The {domain} version changed before Apply.")


def _raise_if_claim_mismatched(request: OrderReopenApplyRequest, claim: CommandClaimState) -> None:
    if claim is CommandClaimState.MISMATCH:
        raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was used by a different command.")


def _raise_if_claim_incomplete(request: OrderReopenApplyRequest, claim: CommandClaimState) -> None:
    if claim is CommandClaimState.MATCHED:
        raise _workflow_error(request, ErrorCategory.INTERNAL, "idempotency_evidence_incomplete", "The reopen claim exists without its receipt.")


def _command_fingerprint(request: OrderReopenApplyRequest) -> PreviewFingerprint:
    return fingerprint_payload({"actor": request.actor.actor_id, "case_no": request.case_no, "client_finance_version": request.expected_client_finance_version.value, "order_version": request.expected_order_version.value, "payroll_version": request.expected_payroll_version.value, "preview_fingerprint": request.preview_fingerprint.value, "reason": request.reason})


def _candidate_workflow_error(request: OrderReopenApplyRequest, error: ReopenCandidateError) -> ReopenWorkflowError:
    code = error.blocker.value
    return ReopenWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, code, "The order cannot be reopened from the current root facts.", request.correlation_id, domain_blockers=(code,)))


def _workflow_error(request: OrderReopenApplyRequest, category: ErrorCategory, code: str, message: str) -> ReopenWorkflowError:
    return ReopenWorkflowError(TypedError(category, code, message, request.correlation_id))


__all__ = [name for name in globals() if name.startswith(("OrderReopen", "Reopen")) or name in {"StoredReopenReceipt"}]

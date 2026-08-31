"""Canonical Orders cancellation workflow and cross-Domain transaction contract."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Callable, Protocol

from domains.client_finance.obligation_planning import (
    ClientFinanceTermsCandidate,
    ClientFinanceTermsSourceFacts,
    build_client_finance_cancellation_impact,
)
from domains.orders.cancellation import (
    CancellationBlocker,
    CancellationCandidate,
    CancellationCandidateError,
    CancellationOrderFacts,
    CancellationSchedulingFacts,
    ConfirmedServiceDay,
    build_cancellation_candidate,
)
from domains.orders.lifecycle import OrderLifecycleRootFacts, OrderLifecycleStatus
from domains.orders.terms import OrderTerms
from shared_kernel.clock import BusinessClock
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text
from subsystems.orders.terms_workflow import (
    ClientFinanceImpactPersistenceCommand,
    CommandClaimState,
    PayrollImpactPersistenceCommand,
    SchedulingReplacementCommand,
    SchedulingReplacementResult,
)
from subsystems.payroll.terms_impact import (
    PayrollTermsImpactCandidate,
    PayrollTermsSourceFacts,
    build_payroll_cancellation_impact,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_REASON_MAXIMUM_LENGTH = 500
_CANCELLATION_SOURCE_EVENT_FAMILY = "orders_cancellation"


@dataclass(frozen=True, slots=True)
class CancellationWorkflowFacts:
    order: CancellationOrderFacts
    order_terms: OrderTerms
    scheduling: CancellationSchedulingFacts
    client_finance: ClientFinanceTermsSourceFacts
    payroll: PayrollTermsSourceFacts
    lifecycle: OrderLifecycleRootFacts
    historical_cancellation_origin: bool = False

    def __post_init__(self) -> None:
        if len({self.order.case_no, self.scheduling.case_no, self.client_finance.case_no, self.payroll.case_no, self.lifecycle.case_no}) != 1:
            raise ValueError("cancellation_workflow_case_mismatch")
        if not isinstance(self.historical_cancellation_origin, bool):
            raise TypeError("historical cancellation origin must be bool")


@dataclass(frozen=True, slots=True)
class CancellationLifecycleImpact:
    case_no: str
    before_status: OrderLifecycleStatus
    after_status: OrderLifecycleStatus
    actual_end_date: date | None
    cancellation_effective: bool
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class OrderCancellationPreview:
    candidate: CancellationCandidate
    client_finance_impact: ClientFinanceTermsCandidate
    payroll_impact: PayrollTermsImpactCandidate
    lifecycle_impact: CancellationLifecycleImpact
    order_version: int
    scheduling_version: int
    client_finance_version: int
    payroll_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class OrderCancellationApplyRequest:
    case_no: str
    confirmed_service_days: tuple[ConfirmedServiceDay, ...]
    expected_order_version: ExpectedVersion
    expected_scheduling_version: ExpectedVersion
    expected_client_finance_version: ExpectedVersion
    expected_payroll_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        require_canonical_text(self.reason, "cancellation reason", _REASON_MAXIMUM_LENGTH)
        if not isinstance(self.confirmed_service_days, tuple):
            raise TypeError("confirmed service days must be a tuple")


@dataclass(frozen=True, slots=True)
class OrderCancellationReceipt:
    case_no: str
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int
    payroll_version: int
    lifecycle_status: OrderLifecycleStatus
    actual_end_date: date | None
    official_service_day_count: int
    official_service_hours: int
    cancelled_assignment_ids: tuple[int, ...]
    created_assignment_keys: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredCancellationReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: OrderCancellationReceipt


@dataclass(frozen=True, slots=True)
class CancellationOrderPersistenceCommand:
    case_no: str
    expected_order_version: int
    resulting_order_version: int
    actual_start_date: date | None
    actual_end_date: date | None
    lifecycle_status: OrderLifecycleStatus


@dataclass(frozen=True, slots=True)
class CancellationReceiptPersistenceCommand:
    key: IdempotencyKey
    stored_receipt: StoredCancellationReceipt
    cancellation_event_id: int
    scheduling_receipt_id: int
    cancellation_control_event_id: int
    lifecycle_event_id: int
    correlation_id: CorrelationId


class CancellationWorkflowRepository(Protocol):
    def load_for_preview(self, case_no: str, requested_staff_ids: tuple[int, ...]) -> CancellationWorkflowFacts: ...
    def preflight_impacted_staff_ids(self, case_no: str, requested_staff_ids: tuple[int, ...]) -> tuple[int, ...]: ...
    def load_for_apply(self, case_no: str, preflight_staff_ids: tuple[int, ...]) -> CancellationWorkflowFacts: ...
    def find_receipt(self, key: IdempotencyKey, *, for_update: bool) -> StoredCancellationReceipt | None: ...
    def claim_command(self, request: OrderCancellationApplyRequest, command_fingerprint: PreviewFingerprint) -> CommandClaimState: ...
    def append_cancellation_event(self, request: OrderCancellationApplyRequest, preview: OrderCancellationPreview) -> int: ...
    def cancel_waiting_deposit_lock(self, request: OrderCancellationApplyRequest, cancellation_event_id: int) -> None: ...
    def replace_scheduling_generation(self, command: SchedulingReplacementCommand) -> SchedulingReplacementResult: ...
    def persist_client_finance_impact(self, command: ClientFinanceImpactPersistenceCommand) -> None: ...
    def persist_payroll_impact(self, command: PayrollImpactPersistenceCommand) -> None: ...
    def activate_cancellation_control(self, request: OrderCancellationApplyRequest, cancellation_event_id: int) -> int: ...
    def persist_cancellation_lifecycle(self, request: OrderCancellationApplyRequest, preview: OrderCancellationPreview, cancellation_control_event_id: int) -> int: ...
    def update_cancelled_order(self, command: CancellationOrderPersistenceCommand) -> None: ...
    def save_receipt(self, command: CancellationReceiptPersistenceCommand) -> None: ...


class CancellationWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class OrderCancellationWorkflow:
    def __init__(self, repository: CancellationWorkflowRepository, unit_of_work_factory: Callable[[], UnitOfWork], clock: BusinessClock) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def preview(self, case_no: str, confirmed_service_days: tuple[ConfirmedServiceDay, ...]) -> OrderCancellationPreview:
        return self._build_preview(self._repository.load_for_preview(case_no, _confirmed_staff_ids(confirmed_service_days)), confirmed_service_days)

    def apply(self, request: OrderCancellationApplyRequest) -> OrderCancellationReceipt:
        command_fingerprint = _command_fingerprint(request)
        preflight_staff_ids = self._preflight_staff_ids(request)
        with self._unit_of_work_factory() as unit_of_work:
            claim_state = self._repository.claim_command(request, command_fingerprint)
            _raise_if_claim_mismatched(request, claim_state)
            replay = self._find_replay(request, command_fingerprint)
            if replay is not None:
                return replay
            _raise_if_claim_incomplete(request, claim_state)
            facts = self._repository.load_for_apply(request.case_no, preflight_staff_ids)
            preview = self._fresh_preview(request, facts, preflight_staff_ids)
            receipt = _build_receipt(preview)
            self._persist(request, preview, command_fingerprint, receipt)
            unit_of_work.commit()
            return receipt

    def _preflight_staff_ids(self, request: OrderCancellationApplyRequest) -> tuple[int, ...]:
        return self._repository.preflight_impacted_staff_ids(request.case_no, _confirmed_staff_ids(request.confirmed_service_days))

    def _find_replay(self, request: OrderCancellationApplyRequest, command_fingerprint: PreviewFingerprint) -> OrderCancellationReceipt | None:
        stored = self._repository.find_receipt(request.idempotency_key, for_update=True)
        if stored is None:
            return None
        if stored.command_fingerprint == command_fingerprint:
            return stored.receipt
        raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")

    def _fresh_preview(self, request: OrderCancellationApplyRequest, facts: CancellationWorkflowFacts, preflight_staff_ids: tuple[int, ...]) -> OrderCancellationPreview:
        _validate_locked_staff_set(request, facts, preflight_staff_ids)
        _validate_expected_versions(request, facts)
        try:
            preview = self._build_preview(facts, request.confirmed_service_days)
        except CancellationCandidateError as error:
            raise _candidate_workflow_error(request, error) from error
        if preview.fingerprint != request.preview_fingerprint:
            raise _workflow_error(request, ErrorCategory.CONFLICT, "stale_preview", "The business facts changed after Preview.")
        _raise_if_impacts_blocked(request, preview)
        return preview

    def _build_preview(self, facts: CancellationWorkflowFacts, confirmed_service_days: tuple[ConfirmedServiceDay, ...]) -> OrderCancellationPreview:
        effective_order = _effective_order_facts(facts, confirmed_service_days)
        try:
            candidate = build_cancellation_candidate(effective_order, facts.scheduling, self._clock.now().date(), confirmed_service_days)
            finance, payroll = _build_impacts(facts, candidate)
        except ValueError as error:
            if str(error) != "payroll_rate_policy_not_found":
                raise
            raise CancellationCandidateError(CancellationBlocker.PAYROLL_RATE_POLICY_NOT_FOUND) from error
        return _preview(facts, candidate, finance, payroll, _build_lifecycle_impact(facts, candidate))

    def _persist(self, request: OrderCancellationApplyRequest, preview: OrderCancellationPreview, command_fingerprint: PreviewFingerprint, receipt: OrderCancellationReceipt) -> None:
        event_id = self._repository.append_cancellation_event(request, preview)
        self._repository.cancel_waiting_deposit_lock(request, event_id)
        scheduling = self._repository.replace_scheduling_generation(_scheduling_command(request, preview, command_fingerprint))
        _persist_finance_and_payroll(self._repository, request, preview, event_id, scheduling)
        control_event_id = self._repository.activate_cancellation_control(request, event_id)
        lifecycle_event_id = self._repository.persist_cancellation_lifecycle(request, preview, control_event_id)
        self._repository.update_cancelled_order(CancellationOrderPersistenceCommand(request.case_no, preview.order_version, receipt.order_version, preview.candidate.actual_start_date, receipt.actual_end_date, receipt.lifecycle_status))
        self._repository.save_receipt(CancellationReceiptPersistenceCommand(request.idempotency_key, StoredCancellationReceipt(command_fingerprint, receipt), event_id, scheduling.scheduling_receipt_id, control_event_id, lifecycle_event_id, request.correlation_id))


def _effective_order_facts(facts, confirmed_service_days):
    order = facts.order
    if order.service_started or not confirmed_service_days:
        return order
    if not facts.historical_cancellation_origin:
        return order
    if facts.lifecycle.current_status is not OrderLifecycleStatus.CANCELLED:
        return order
    actual_start_date = min(item.service_date for item in confirmed_service_days)
    return replace(
        order,
        actual_start_date=actual_start_date,
        service_started=True,
    )


def _build_impacts(facts, candidate):
    change_identity = f"cancellation:{candidate.fingerprint.value}"
    finance = build_client_finance_cancellation_impact(facts.client_finance, facts.order_terms, candidate.scheduling, change_identity)
    payroll = build_payroll_cancellation_impact(facts.payroll, candidate.scheduling, facts.order_terms, change_identity)
    return finance, payroll


def _confirmed_staff_ids(confirmed_service_days):
    return tuple(sorted({item.staff_id for item in confirmed_service_days}))


def _build_lifecycle_impact(facts, candidate):
    payload = {"case_no": facts.order.case_no, "before_status": facts.lifecycle.current_status.value, "after_status": OrderLifecycleStatus.CANCELLED.value, "actual_start_date": candidate.actual_start_date.isoformat() if candidate.actual_start_date else None, "actual_end_date": candidate.actual_end_date.isoformat() if candidate.actual_end_date else None, "cancellation_fingerprint": candidate.fingerprint.value}
    return CancellationLifecycleImpact(facts.order.case_no, facts.lifecycle.current_status, OrderLifecycleStatus.CANCELLED, candidate.actual_end_date, True, fingerprint_payload(payload))


def _preview(facts, candidate, finance, payroll, lifecycle):
    payload = {"cancellation": candidate.fingerprint.value, "client_finance": finance.fingerprint.value, "payroll": payroll.fingerprint.value, "lifecycle": lifecycle.fingerprint.value, "client_finance_version": facts.client_finance.account_version, "payroll_version": facts.payroll.payroll_version}
    return OrderCancellationPreview(candidate, finance, payroll, lifecycle, facts.order.order_version, facts.scheduling.aggregate_version, facts.client_finance.account_version, facts.payroll.payroll_version, fingerprint_payload(payload))


def _scheduling_command(request, preview, command_fingerprint):
    return SchedulingReplacementCommand(preview.candidate.scheduling, "orders_cancellation_rebuild", preview.order_version, command_fingerprint, preview.fingerprint, request.idempotency_key, request.actor, request.reason, request.correlation_id)


def _persist_finance_and_payroll(repository, request, preview, event_id, scheduling):
    _persist_client_finance(repository, request, preview, event_id)
    _persist_payroll(repository, request, preview, event_id, scheduling)


def _persist_client_finance(repository, request, preview, event_id):
    repository.persist_client_finance_impact(ClientFinanceImpactPersistenceCommand(preview.client_finance_impact, request.idempotency_key, request.actor, request.reason, request.correlation_id, _CANCELLATION_SOURCE_EVENT_FAMILY, event_id))


def _persist_payroll(repository, request, preview, event_id, scheduling):
    repository.persist_payroll_impact(PayrollImpactPersistenceCommand(preview.payroll_impact, scheduling.assignment_resolution, request.idempotency_key, request.actor, request.reason, request.correlation_id, event_id))


def _build_receipt(preview):
    scheduling = preview.candidate.scheduling
    return OrderCancellationReceipt(preview.candidate.case_no, preview.order_version + 1, scheduling.resulting_aggregate_version, scheduling.generation_number, preview.client_finance_impact.resulting_account_version, preview.payroll_impact.resulting_payroll_version, OrderLifecycleStatus.CANCELLED, preview.candidate.actual_end_date, preview.candidate.official_service_day_count, preview.candidate.official_service_hours, scheduling.cancelled_assignment_ids, tuple(item.candidate_key for item in scheduling.assignments), preview.fingerprint)


def _validate_expected_versions(request, facts):
    for expected, current, domain in _version_comparisons(request, facts):
        if expected != current:
            raise _workflow_error(request, ErrorCategory.CONFLICT, f"{domain}_version_conflict", f"The {domain} version changed before Apply.")


def _version_comparisons(request, facts):
    return ((request.expected_order_version.value, facts.order.order_version, "order"), (request.expected_scheduling_version.value, facts.scheduling.aggregate_version, "scheduling"), (request.expected_client_finance_version.value, facts.client_finance.account_version, "client_finance"), (request.expected_payroll_version.value, facts.payroll.payroll_version, "payroll"))


def _validate_locked_staff_set(request, facts, preflight_staff_ids):
    current = {item.staff_id for item in facts.scheduling.assignments}
    requested = {item.staff_id for item in request.confirmed_service_days}
    if current.union(requested).issubset(set(preflight_staff_ids)):
        return
    raise _workflow_error(request, ErrorCategory.CONFLICT, "cancellation_lock_set_stale", "The impacted caregiver set expanded after preflight.")


def _raise_if_impacts_blocked(request, preview):
    blockers = tuple(sorted(set(preview.client_finance_impact.blockers).union(preview.payroll_impact.blockers)))
    if blockers:
        raise CancellationWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, "cancellation_impact_blocked", "A downstream Domain blocked the cancellation.", request.correlation_id, domain_blockers=blockers))


def _raise_if_claim_mismatched(request, claim_state):
    if claim_state is CommandClaimState.MISMATCH:
        raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")


def _raise_if_claim_incomplete(request, claim_state):
    if claim_state is CommandClaimState.MATCHED:
        raise _workflow_error(request, ErrorCategory.INTERNAL, "idempotency_evidence_incomplete", "The command claim exists without its receipt.")


def _command_fingerprint(request):
    return fingerprint_payload(_command_payload(request))


def _command_payload(request):
    return {"case_no": request.case_no, "confirmed_service_days": tuple({"service_date": item.service_date.isoformat(), "staff_id": item.staff_id, "reason": item.reason} for item in request.confirmed_service_days), "order_version": request.expected_order_version.value, "scheduling_version": request.expected_scheduling_version.value, "client_finance_version": request.expected_client_finance_version.value, "payroll_version": request.expected_payroll_version.value, "preview_fingerprint": request.preview_fingerprint.value, "actor": request.actor.actor_id, "reason": request.reason}


def _workflow_error(request, category, code, message):
    return CancellationWorkflowError(TypedError(category, code, message, request.correlation_id))


def _candidate_workflow_error(request, error):
    blocker = error.blocker.value
    return CancellationWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, blocker, "The cancellation business facts require human correction.", request.correlation_id, domain_blockers=(blocker,)))


__all__ = [name for name in globals() if name.startswith(("OrderCancellation", "Cancellation")) or name in {"StoredCancellationReceipt"}]

"""Preview and atomic Apply workflow for Actual Start confirmation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Callable, Protocol

from domains.client_finance.obligation_planning import (
    ClientFinanceTermsCandidate,
    build_client_finance_terms_impact,
)
from domains.client_finance.subsidy_coverage import derive_subsidy_coverage
from domains.orders.actual_start import (
    ActualStartAssignmentFacts,
    ActualStartCandidate,
    ActualStartCandidateKind,
    ActualStartOrderFacts,
    ActualStartReconfirmationAction,
    ActualStartReconfirmationCandidate,
    ActualStartReconfirmationFacts,
    ActualStartSchedulingFacts,
    build_actual_start_candidate,
    build_actual_start_reconfirmation_candidate,
    to_scheduling_generation_candidate,
)
from domains.orders.lifecycle import (
    LifecycleImpactCandidate,
    OrderLifecycleStatus,
    build_terms_lifecycle_impact,
)
from domains.payroll.payment_due_date import calculate_staff_payment_due_date
from domains.scheduling.generation import SchedulingGenerationCandidate
from shared_kernel.clock import BusinessClock
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
from subsystems.orders.terms_workflow import (
    ClientFinanceImpactPersistenceCommand,
    CommandClaimState,
    LifecycleImpactPersistenceCommand,
    OrderTermsReceipt,
    PayrollImpactPersistenceCommand,
    SchedulingReplacementCommand,
    SchedulingReplacementResult,
    StoredTermsReceipt,
    TermsWorkflowFacts,
)
from subsystems.payroll.terms_impact import (
    PayrollTermsImpactCandidate,
    build_payroll_terms_impact,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_REASON_MAXIMUM_LENGTH = 500
_ACTUAL_START_SOURCE_EVENT_FAMILY = "order-actual-start"


@dataclass(frozen=True, slots=True)
class ActualStartPreview:
    before_actual_start_date: date | None
    after_actual_start_date: date
    actual_start: ActualStartCandidate
    scheduling: SchedulingGenerationCandidate
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int
    payroll_version: int
    client_finance_impact: ClientFinanceTermsCandidate
    payroll_impact: PayrollTermsImpactCandidate
    lifecycle_impact: LifecycleImpactCandidate
    reconfirmation: ActualStartReconfirmationCandidate
    client_identity_status: str
    is_full_subsidy_order: bool
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ActualStartWorkflowContext:
    shared_facts: TermsWorkflowFacts
    reconfirmation: ActualStartReconfirmationFacts | None


@dataclass(frozen=True, slots=True)
class ActualStartApplyRequest:
    case_no: str
    new_actual_start_date: date
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
        require_canonical_text(self.reason, "change reason", _REASON_MAXIMUM_LENGTH)
        if not isinstance(self.new_actual_start_date, date):
            raise TypeError("new actual start date must be a date")


@dataclass(frozen=True, slots=True)
class ActualStartPersistenceCommand:
    case_no: str
    actual_start_date: date
    actual_end_date: date
    staff_payment_due_date: date | None
    lifecycle_status: OrderLifecycleStatus
    expected_order_version: int
    resulting_order_version: int


@dataclass(frozen=True, slots=True)
class ActualStartReceiptPersistenceCommand:
    key: IdempotencyKey
    stored_receipt: StoredTermsReceipt
    actual_start_event_id: int
    scheduling_receipt_id: int
    lifecycle_event_id: int
    control_event_id: int | None
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ConfirmActualStartReconfirmationCommand:
    case_no: str
    required_settlement_identity: PreviewFingerprint
    reconfirmation_fingerprint: PreviewFingerprint
    actual_start_event_id: int
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


class ActualStartReconfirmationControlPort(Protocol):
    def confirm_actual_start_reconfirmation(
        self, command: ConfirmActualStartReconfirmationCommand
    ) -> int: ...


class ActualStartWorkflowRepository(ActualStartReconfirmationControlPort, Protocol):
    def load_for_preview(self, case_no: str) -> ActualStartWorkflowContext: ...
    def preflight_impacted_staff_ids(self, case_no: str) -> tuple[int, ...]: ...
    def load_for_apply(
        self, case_no: str, preflight_staff_ids: tuple[int, ...]
    ) -> ActualStartWorkflowContext: ...
    def claim_actual_start_command(
        self, request: ActualStartApplyRequest, command_fingerprint: PreviewFingerprint
    ) -> CommandClaimState: ...
    def find_actual_start_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredTermsReceipt | None: ...
    def append_actual_start_event(
        self, request: ActualStartApplyRequest, preview: ActualStartPreview
    ) -> int: ...
    def replace_scheduling_generation(
        self, command: SchedulingReplacementCommand
    ) -> SchedulingReplacementResult: ...
    def persist_client_finance_impact(
        self, command: ClientFinanceImpactPersistenceCommand
    ) -> None: ...
    def persist_payroll_impact(self, command: PayrollImpactPersistenceCommand) -> None: ...
    def persist_lifecycle_impact(
        self, command: LifecycleImpactPersistenceCommand
    ) -> int: ...
    def update_actual_start(self, command: ActualStartPersistenceCommand) -> None: ...
    def save_actual_start_receipt(
        self, command: ActualStartReceiptPersistenceCommand
    ) -> None: ...


class ActualStartWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class ActualStartWorkflow:
    def __init__(
        self,
        repository: ActualStartWorkflowRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
        clock: BusinessClock,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def preview(
        self,
        case_no: str,
        new_date: date,
        *,
        recalculated_service_dates: tuple[date, ...] | None = None,
    ) -> ActualStartPreview:
        return self._build_preview(
            self._repository.load_for_preview(case_no),
            new_date,
            recalculated_service_dates,
        )

    def apply(
        self,
        request: ActualStartApplyRequest,
        *,
        recalculated_service_dates: tuple[date, ...] | None = None,
    ) -> OrderTermsReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self.apply_in_current_unit_of_work(
                request,
                recalculated_service_dates=recalculated_service_dates,
            )
            unit_of_work.commit()
            return receipt

    def apply_in_current_unit_of_work(
        self,
        request: ActualStartApplyRequest,
        *,
        recalculated_service_dates: tuple[date, ...] | None = None,
    ) -> OrderTermsReceipt:
        """Apply under a caller-owned outer transaction without a nested commit."""
        command_fingerprint = _command_fingerprint(request)
        staff_ids = self._repository.preflight_impacted_staff_ids(request.case_no)
        replay = self._claim_or_replay(request, command_fingerprint)
        if replay is not None:
            return replay
        context = self._repository.load_for_apply(request.case_no, staff_ids)
        preview = self._fresh_preview(
            request,
            context,
            staff_ids,
            recalculated_service_dates,
        )
        receipt = _build_receipt(preview)
        self._persist(request, preview, command_fingerprint, receipt)
        return receipt

    def _claim_or_replay(self, request, command_fingerprint):
        state = self._repository.claim_actual_start_command(request, command_fingerprint)
        if state is CommandClaimState.MISMATCH:
            raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")
        stored = self._repository.find_actual_start_receipt(request.idempotency_key, for_update=True)
        if stored is not None:
            return _matched_receipt(request, command_fingerprint, stored)
        if state is CommandClaimState.MATCHED:
            _raise_missing_receipt(request)
        return None

    def _fresh_preview(
        self,
        request,
        context,
        staff_ids,
        recalculated_service_dates=None,
    ):
        _validate_locked_staff_set(request, context.shared_facts, staff_ids)
        _validate_versions(request, context.shared_facts)
        preview = self._build_preview(
            context,
            request.new_actual_start_date,
            recalculated_service_dates,
        )
        if preview.fingerprint != request.preview_fingerprint:
            raise _workflow_error(request, ErrorCategory.CONFLICT, "stale_preview", "The business facts changed after Preview.")
        _raise_if_impacts_blocked(request, preview)
        return preview

    def _build_preview(self, context, new_date, recalculated_service_dates=None):
        facts = context.shared_facts
        reconfirmation = build_actual_start_reconfirmation_candidate(context.reconfirmation)
        actual_start, scheduling = _actual_start_candidates(
            facts,
            new_date,
            recalculated_service_dates,
        )
        client_finance, payroll = _downstream_impacts(facts, actual_start, scheduling)
        lifecycle = _actual_start_lifecycle(facts, new_date, scheduling, client_finance, self._clock)
        return _preview_result(facts, actual_start, scheduling, client_finance, payroll, lifecycle, reconfirmation)

    def _persist(self, request, preview, command_fingerprint, receipt):
        event_id = self._repository.append_actual_start_event(request, preview)
        scheduling_result = _persist_scheduling(self._repository, request, preview, command_fingerprint)
        _persist_finance_and_payroll(self._repository, request, preview, event_id, scheduling_result.assignment_resolution)
        control_event_id = _confirm_reconfirmation(self._repository, request, preview, event_id)
        lifecycle_id = _persist_lifecycle(self._repository, request, preview, receipt)
        _persist_order_projection(self._repository, request, preview, receipt)
        _persist_receipt(self._repository, request, command_fingerprint, receipt, event_id, scheduling_result.scheduling_receipt_id, lifecycle_id, control_event_id)


def _actual_start_candidates(facts, new_date, recalculated_service_dates=None):
    actual_start = build_actual_start_candidate(
        _actual_start_order_facts(facts),
        _actual_start_scheduling_facts(facts),
        new_date,
        facts.order.terms.service_hours_per_day,
        recalculated_service_dates,
    )
    return actual_start, to_scheduling_generation_candidate(actual_start)


def _raise_missing_receipt(request):
    raise _workflow_error(request, ErrorCategory.INTERNAL, "idempotency_evidence_incomplete", "The command claim exists without its receipt.")


def _actual_start_lifecycle(facts, new_date, scheduling, client, clock):
    roots = replace(facts.lifecycle, actual_start_date=new_date, actual_start_reconfirmed=True)
    return build_terms_lifecycle_impact(roots, facts.order.terms, scheduling, client.settlement, clock.now())


def _persist_scheduling(repository, request, preview, command_fingerprint):
    command = SchedulingReplacementCommand(
        candidate=preview.scheduling,
        command_family="orders_actual_start_rebuild",
        expected_order_version=preview.order_version,
        command_fingerprint=command_fingerprint,
        preview_fingerprint=preview.fingerprint,
        idempotency_key=request.idempotency_key,
        actor=request.actor,
        reason=request.reason,
        correlation_id=request.correlation_id,
    )
    return repository.replace_scheduling_generation(command)


def _persist_lifecycle(repository, request, preview, receipt):
    command = LifecycleImpactPersistenceCommand(
        candidate=preview.lifecycle_impact,
        expected_order_version=preview.order_version,
        resulting_order_version=receipt.order_version,
        client_settlement_fingerprint=preview.client_finance_impact.settlement.fingerprint,
        idempotency_key=request.idempotency_key,
        actor=request.actor,
        reason=request.reason,
        correlation_id=request.correlation_id,
        trigger_event=_actual_start_trigger_event(preview),
    )
    return repository.persist_lifecycle_impact(command)


def _actual_start_trigger_event(preview):
    if preview.actual_start.kind is ActualStartCandidateKind.FIRST_CONFIRMATION:
        return "actual_start_confirmed"
    return "actual_start_corrected"


def _persist_order_projection(repository, request, preview, receipt):
    repository.update_actual_start(
        ActualStartPersistenceCommand(
            request.case_no,
            request.new_actual_start_date,
            preview.actual_start.actual_end_date,
            _staff_payment_due_date(preview),
            preview.lifecycle_impact.after_status,
            preview.order_version,
            receipt.order_version,
        )
    )


def _staff_payment_due_date(preview):
    return _calculated_staff_payment_due_date(
        preview.actual_start.actual_end_date,
        preview.client_finance_impact,
        preview.is_full_subsidy_order,
    )


def _calculated_staff_payment_due_date(
    actual_end_date,
    client_finance_impact,
    is_full_subsidy_order,
):
    client_payable_amount = sum(
        (stage_plan.amount.amount for stage_plan in client_finance_impact.stage_plans),
        0,
    )
    return calculate_staff_payment_due_date(
        actual_end_date,
        client_payable_amount,
        is_full_subsidy_order,
    )


def _persist_receipt(repository, request, command_fingerprint, receipt, event_id, scheduling_receipt_id, lifecycle_id, control_event_id):
    repository.save_actual_start_receipt(ActualStartReceiptPersistenceCommand(request.idempotency_key, StoredTermsReceipt(command_fingerprint, receipt), event_id, scheduling_receipt_id, lifecycle_id, control_event_id, request.correlation_id))


def _actual_start_order_facts(facts):
    return ActualStartOrderFacts(facts.order.case_no, facts.order.version, facts.lifecycle.actual_start_date, facts.order.service_data_locked, facts.order.terms.service_time)


def _actual_start_scheduling_facts(facts):
    assignments = _actual_start_assignments(facts)
    root_date = facts.lifecycle.actual_start_date or facts.order.terms.planned_start_date
    return ActualStartSchedulingFacts(facts.order.case_no, facts.scheduling.aggregate_version, facts.scheduling.generation_number, root_date, assignments)


def _actual_start_assignments(facts):
    service_dates = facts.planned_service_dates
    assignments = []
    offset = 0
    for segment in sorted(facts.scheduling.segments, key=lambda item: item.sequence):
        end = offset + segment.service_day_count
        assignments.append(ActualStartAssignmentFacts(segment.assignment_id, segment.staff_id, segment.sequence, segment.assigned_start_date, segment.assigned_end_date, service_dates[offset:end]))
        offset = end
    return tuple(assignments)


def _downstream_impacts(facts, actual_start, scheduling):
    change_identity = f"actual-start:{actual_start.fingerprint.value}"
    client = _client_finance_impact(
        facts,
        actual_start,
        scheduling,
        change_identity,
    )
    coverage = _subsidy_coverage(facts)
    staff_payment_due_date = _calculated_staff_payment_due_date(
        actual_start.actual_end_date,
        client,
        coverage.is_full_subsidy_order,
    )
    return client, _payroll_impact(
        facts,
        scheduling,
        change_identity,
        staff_payment_due_date,
    )


def _client_finance_impact(facts, actual_start, scheduling, change_identity):
    payment_terms = replace(facts.client_finance.payment_terms, first_payment_due_date=actual_start.new_actual_start_date, second_payment_due_date=actual_start.actual_end_date)
    client_source = replace(facts.client_finance, payment_terms=payment_terms, double_pay_dates=())
    return build_client_finance_terms_impact(client_source, facts.order.terms, scheduling, change_identity)


def _payroll_impact(
    facts,
    scheduling,
    change_identity,
    staff_payment_due_date,
):
    payroll_source = replace(
        facts.payroll,
        staff_payment_due_date=staff_payment_due_date,
        source_terms=tuple(
            replace(item, double_pay_dates=())
            for item in facts.payroll.source_terms
        ),
    )
    return build_payroll_terms_impact(payroll_source, scheduling, facts.order.terms, change_identity)


def _subsidy_coverage(facts):
    return derive_subsidy_coverage(
        facts.order.client_identity_status,
        Decimal(facts.order.terms.service_days * facts.order.terms.service_hours_per_day),
        Decimal(facts.order.terms.floor_fee.amount),
    )


def _preview_result(facts, actual_start, scheduling, client, payroll, lifecycle, reconfirmation):
    payload = _preview_fingerprint_payload(facts, actual_start, client, payroll, lifecycle, reconfirmation)
    coverage = _subsidy_coverage(facts)
    return ActualStartPreview(facts.lifecycle.actual_start_date, actual_start.new_actual_start_date, actual_start, scheduling, facts.order.version, facts.scheduling.aggregate_version, facts.scheduling.generation_number, facts.client_finance.account_version, facts.payroll.payroll_version, client, payroll, lifecycle, reconfirmation, facts.order.client_identity_status, coverage.is_full_subsidy_order, fingerprint_payload(payload))


def _preview_fingerprint_payload(facts, actual_start, client, payroll, lifecycle, reconfirmation):
    return {"actual_start": actual_start.fingerprint.value, "client_finance": client.fingerprint.value, "payroll": payroll.fingerprint.value, "lifecycle": lifecycle.fingerprint.value, "reconfirmation": reconfirmation.fingerprint.value, "order_version": facts.order.version, "scheduling_version": facts.scheduling.aggregate_version, "client_finance_version": facts.client_finance.account_version, "payroll_version": facts.payroll.payroll_version}


def _confirm_reconfirmation(repository, request, preview, actual_start_event_id):
    candidate = preview.reconfirmation
    if candidate.action is ActualStartReconfirmationAction.NO_OP:
        return None
    settlement_identity = candidate.settlement_identity
    if settlement_identity is None:
        raise ValueError("active reconfirmation settlement identity is missing")
    return repository.confirm_actual_start_reconfirmation(_confirmation_command(request, candidate, settlement_identity, actual_start_event_id))


def _confirmation_command(request, candidate, settlement_identity, actual_start_event_id):
    return ConfirmActualStartReconfirmationCommand(case_no=request.case_no, required_settlement_identity=settlement_identity, reconfirmation_fingerprint=candidate.fingerprint, actual_start_event_id=actual_start_event_id, idempotency_key=request.idempotency_key, actor=request.actor, reason=request.reason, correlation_id=request.correlation_id)


def _persist_finance_and_payroll(repository, request, preview, event_id, assignment_resolution):
    _persist_client_finance(repository, request, preview, event_id)
    _persist_payroll(repository, request, preview, event_id, assignment_resolution)


def _persist_client_finance(repository, request, preview, event_id):
    repository.persist_client_finance_impact(ClientFinanceImpactPersistenceCommand(candidate=preview.client_finance_impact, idempotency_key=request.idempotency_key, actor=request.actor, reason=request.reason, correlation_id=request.correlation_id, source_event_family=_ACTUAL_START_SOURCE_EVENT_FAMILY, source_event_id=event_id))


def _persist_payroll(repository, request, preview, event_id, assignment_resolution):
    repository.persist_payroll_impact(PayrollImpactPersistenceCommand(candidate=preview.payroll_impact, assignment_resolution=assignment_resolution, idempotency_key=request.idempotency_key, actor=request.actor, reason=request.reason, correlation_id=request.correlation_id, source_event_id=event_id))


def _build_receipt(preview):
    assignments = preview.scheduling.assignments
    return OrderTermsReceipt(preview.scheduling.case_no, preview.order_version + 1, preview.scheduling.resulting_aggregate_version, preview.scheduling.generation_number, preview.client_finance_impact.resulting_account_version, preview.payroll_impact.resulting_payroll_version, preview.lifecycle_impact.after_status, preview.lifecycle_impact.service_data_lock_should_exist and not preview.lifecycle_impact.service_data_lock_was_present, preview.scheduling.cancelled_assignment_ids, tuple(item.candidate_key for item in assignments), sum(len(item.service_dates) for item in assignments), sum(item.actual_hours for item in assignments), preview.fingerprint)


def _validate_versions(request, facts):
    for expected, current, domain in _version_comparisons(request, facts):
        _validate_version(request, expected, current, domain)


def _version_comparisons(request, facts):
    return ((request.expected_order_version.value, facts.order.version, "order"), (request.expected_scheduling_version.value, facts.scheduling.aggregate_version, "scheduling"), (request.expected_client_finance_version.value, facts.client_finance.account_version, "client_finance"), (request.expected_payroll_version.value, facts.payroll.payroll_version, "payroll"))


def _validate_version(request, expected, current, domain):
    if expected == current:
        return
    code = "client_finance_candidate_stale" if domain == "client_finance" else f"{domain}_version_conflict"
    raise _workflow_error(request, ErrorCategory.CONFLICT, code, f"The {domain} version changed before Apply.")


def _validate_locked_staff_set(request, facts, staff_ids):
    current = {segment.staff_id for segment in facts.scheduling.segments}
    if current.issubset(set(staff_ids)):
        return
    raise _workflow_error(request, ErrorCategory.CONFLICT, "scheduling_lock_set_stale", "The impacted caregiver set expanded after preflight.")


def _raise_if_impacts_blocked(request, preview):
    blockers = tuple(sorted(set(preview.client_finance_impact.blockers) | set(preview.payroll_impact.blockers)))
    if not blockers:
        return
    raise ActualStartWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, "actual_start_impact_blocked", "A downstream Domain blocked the Actual Start change.", request.correlation_id, domain_blockers=blockers))


def _command_fingerprint(request):
    return fingerprint_payload({"case_no": request.case_no, "new_actual_start_date": request.new_actual_start_date.isoformat(), "order_version": request.expected_order_version.value, "scheduling_version": request.expected_scheduling_version.value, "client_finance_version": request.expected_client_finance_version.value, "payroll_version": request.expected_payroll_version.value, "preview_fingerprint": request.preview_fingerprint.value, "actor": request.actor.actor_id, "reason": request.reason})


def _matched_receipt(request, command_fingerprint, stored):
    if stored.command_fingerprint == command_fingerprint:
        return stored.receipt
    raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")


def _workflow_error(request, category, code, message):
    return ActualStartWorkflowError(TypedError(category, code, message, request.correlation_id))


__all__ = [
    "ActualStartApplyRequest",
    "ActualStartReconfirmationControlPort",
    "ActualStartPersistenceCommand",
    "ActualStartPreview",
    "ActualStartReceiptPersistenceCommand",
    "ActualStartWorkflowContext",
    "ActualStartWorkflow",
    "ActualStartWorkflowError",
    "ConfirmActualStartReconfirmationCommand",
]

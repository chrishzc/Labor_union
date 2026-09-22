"""Preview and atomic Apply workflow for Actual Start confirmation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Callable, Protocol

from domains.client_finance.obligation_planning import (
    ClientSettlementProjection,
)
from domains.client_finance.reconciliation import PaymentStage
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
from domains.scheduling.generation import EffectiveAssignmentSegment
from domains.orders.lifecycle import (
    LifecycleImpactCandidate,
    OrderLifecycleStatus,
    build_terms_lifecycle_impact,
)
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
    CommandClaimState,
    LifecycleImpactPersistenceCommand,
    OrderTermsReceipt,
    SchedulingReplacementCommand,
    SchedulingReplacementResult,
    StoredTermsReceipt,
    TermsWorkflowFacts,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_REASON_MAXIMUM_LENGTH = 500


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
    client_settlement: ClientSettlementProjection
    lifecycle_impact: LifecycleImpactCandidate
    reconfirmation: ActualStartReconfirmationCandidate
    unpersisted_source_assignment_ids: tuple[int, ...]
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ActualStartWorkflowContext:
    shared_facts: TermsWorkflowFacts
    reconfirmation: ActualStartReconfirmationFacts | None
    unpersisted_source_assignment_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ActualStartQueryFacts:
    case_no: str
    current_actual_start_date: date | None
    planned_start_date: date
    service_data_locked: bool
    order_version: int
    scheduling_version: int | None
    scheduling_generation: int | None
    client_finance_version: int | None
    payroll_version: int | None
    has_formal_assignments: bool
    historical_precision_restarted: bool


@dataclass(frozen=True, slots=True)
class ActualStartDateOnlyPreview:
    case_no: str
    before_actual_start_date: date | None
    after_actual_start_date: date
    order_version: int
    scheduling_version: int | None
    scheduling_generation: int | None
    client_finance_version: int | None
    payroll_version: int | None
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ActualStartDateOnlyResult:
    case_no: str
    actual_start_date: date
    order_version: int
    scheduling_version: int | None
    scheduling_generation: int | None
    client_finance_version: int | None
    payroll_version: int | None
    preview_fingerprint: PreviewFingerprint
    changed: bool


@dataclass(frozen=True, slots=True)
class ActualStartDateOnlyApplyRequest:
    case_no: str
    new_actual_start_date: date
    expected_order_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        if not isinstance(self.new_actual_start_date, date):
            raise TypeError("new actual start date must be a date")


@dataclass(frozen=True, slots=True)
class ActualStartDateOnlyPersistenceCommand:
    case_no: str
    actual_start_date: date
    expected_order_version: int
    resulting_order_version: int
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class HistoricalActualStartSourceAssignment:
    source_assignment_id: int | None
    staff_id: int


@dataclass(frozen=True, slots=True)
class ActualStartApplyRequest:
    case_no: str
    new_actual_start_date: date
    expected_order_version: ExpectedVersion
    expected_scheduling_version: ExpectedVersion
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
    def load_actual_start_query(
        self, case_no: str, *, for_update: bool
    ) -> ActualStartQueryFacts: ...
    def save_actual_start_date_only(
        self, command: ActualStartDateOnlyPersistenceCommand
    ) -> None: ...
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

    def preview_date_only(
        self,
        facts: ActualStartQueryFacts,
        new_date: date,
    ) -> ActualStartDateOnlyPreview:
        return _date_only_preview(facts, new_date)

    def apply_date_only(
        self,
        request: ActualStartDateOnlyApplyRequest,
    ) -> ActualStartDateOnlyResult:
        with self._unit_of_work_factory() as unit_of_work:
            facts = self._repository.load_actual_start_query(
                request.case_no,
                for_update=True,
            )
            if facts.order_version != request.expected_order_version.value:
                raise _workflow_error(
                    request,
                    ErrorCategory.CONFLICT,
                    "order_version_conflict",
                    "The Orders root changed after Preview.",
                    current_version=facts.order_version,
                )
            preview = _date_only_preview(
                facts,
                request.new_actual_start_date,
                correlation_id=request.correlation_id,
            )
            if preview.fingerprint != request.preview_fingerprint:
                raise _workflow_error(
                    request,
                    ErrorCategory.CONFLICT,
                    "stale_preview",
                    "The Actual Start date-only facts changed after Preview.",
                )
            changed = facts.current_actual_start_date != request.new_actual_start_date
            resulting_version = facts.order_version + 1 if changed else facts.order_version
            if changed:
                self._repository.save_actual_start_date_only(
                    ActualStartDateOnlyPersistenceCommand(
                        request.case_no,
                        request.new_actual_start_date,
                        facts.order_version,
                        resulting_version,
                        request.correlation_id,
                    )
                )
            unit_of_work.commit()
            return ActualStartDateOnlyResult(
                request.case_no,
                request.new_actual_start_date,
                resulting_version,
                facts.scheduling_version,
                facts.scheduling_generation,
                facts.client_finance_version,
                facts.payroll_version,
                preview.fingerprint,
                changed,
            )

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

    def preview_historical_source(
        self,
        case_no: str,
        new_date: date,
        *,
        recalculated_service_dates: tuple[date, ...],
        source_staff_ids: tuple[int, ...],
        source_assignment_ids: tuple[int | None, ...] = (),
    ) -> ActualStartPreview:
        """Validate an unpersisted historical caregiver source without writes.

        Historical workbook Preview runs before its source assignment exists in
        Scheduling.  It therefore projects the same canonical service dates
        and rate-policy bindings into an in-memory Scheduling snapshot solely
        for the Actual Start/Finance/Payroll candidate calculation.
        """
        context = self._repository.load_for_preview(case_no)
        return self._build_preview(
            _historical_source_context(
                context,
                recalculated_service_dates,
                source_staff_ids,
                source_assignment_ids,
            ),
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

    def replay_from_immutable_source(
        self, idempotency_key: IdempotencyKey
    ) -> OrderTermsReceipt | None:
        """Return a completed receipt for a caller-owned immutable source.

        Historical adoption derives this key from the immutable workbook row.
        Its current versions necessarily differ after a successful Actual Start,
        so it must read a completed receipt before constructing a fresh command.
        """
        stored = self._repository.find_actual_start_receipt(
            idempotency_key, for_update=True
        )
        return None if stored is None else stored.receipt

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

    def apply_historical_source_in_current_unit_of_work(
        self,
        request: ActualStartApplyRequest,
        *,
        recalculated_service_dates: tuple[date, ...],
        source_staff_ids: tuple[int, ...] = (),
        source_assignment_ids: tuple[int | None, ...] = (),
    ) -> OrderTermsReceipt:
        """Apply a historical source through the canonical writer in one UoW.

        Historical adoption may have a source assignment that is not present in
        the current Scheduling generation yet.  The source context used by
        ``preview_historical_source`` is therefore rebuilt after the command
        claim and fresh locks, instead of asking the generic Apply path to
        interpret the stale formal root.  Persistence remains the same
        canonical ``_persist`` sequence as ordinary Actual Start.
        """
        command_fingerprint = _command_fingerprint(request)
        preflight_staff_ids = self._repository.preflight_impacted_staff_ids(
            request.case_no
        )
        replay = self._claim_or_replay(request, command_fingerprint)
        if replay is not None:
            return replay
        # A historical source caregiver may not be visible to the ordinary
        # effective-generation preflight query.  Include it in the same locked
        # set so the fresh source context cannot race a staff mutation.
        locked_staff_ids = tuple(
            sorted(set(preflight_staff_ids) | set(source_staff_ids))
        )
        context = self._repository.load_for_apply(
            request.case_no,
            locked_staff_ids,
        )
        historical_context = _historical_source_context(
            context,
            recalculated_service_dates,
            source_staff_ids,
            source_assignment_ids,
        )
        preview = self._fresh_preview(
            request,
            historical_context,
            locked_staff_ids,
            recalculated_service_dates,
        )
        receipt = _build_receipt(preview)
        self._persist(request, preview, command_fingerprint, receipt)
        return receipt

    def apply_historical_source(
        self,
        request: ActualStartApplyRequest,
        *,
        source_loader: Callable[
            [],
            tuple[
                tuple[date, ...],
                tuple[HistoricalActualStartSourceAssignment, ...],
            ],
        ],
    ) -> OrderTermsReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            recalculated_service_dates, assignments = source_loader()
            receipt = self.apply_historical_source_in_current_unit_of_work(
                request,
                recalculated_service_dates=recalculated_service_dates,
                source_staff_ids=tuple(item.staff_id for item in assignments),
                source_assignment_ids=tuple(
                    item.source_assignment_id for item in assignments
                ),
            )
            unit_of_work.commit()
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
        return preview

    def _build_preview(self, context, new_date, recalculated_service_dates=None):
        facts = context.shared_facts
        reconfirmation = build_actual_start_reconfirmation_candidate(context.reconfirmation)
        actual_start, scheduling = _actual_start_candidates(
            facts,
            new_date,
            recalculated_service_dates,
        )
        client_settlement = _existing_client_settlement(facts)
        lifecycle = _actual_start_lifecycle(
            facts,
            new_date,
            scheduling,
            client_settlement,
            self._clock,
        )
        return _preview_result(
            facts,
            actual_start,
            scheduling,
            client_settlement,
            lifecycle,
            reconfirmation,
            context.unpersisted_source_assignment_ids,
        )

    def _persist(self, request, preview, command_fingerprint, receipt):
        event_id = self._repository.append_actual_start_event(request, preview)
        scheduling_result = _persist_scheduling(self._repository, request, preview, command_fingerprint)
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


def _date_only_preview(facts, new_date, *, correlation_id=None):
    if not isinstance(facts, ActualStartQueryFacts):
        raise TypeError("actual start query facts are invalid")
    if not isinstance(new_date, date):
        raise TypeError("new actual start date must be a date")
    if facts.service_data_locked:
        raise ActualStartCandidateError(ActualStartBlocker.SERVICE_DATA_LOCKED)
    if facts.has_formal_assignments or facts.historical_precision_restarted:
        code = (
            "historical_actual_start_requires_reschedule"
            if facts.historical_precision_restarted
            else "actual_start_mode_changed"
        )
        if correlation_id is None:
            raise ValueError(code)
        raise ActualStartWorkflowError(TypedError(
            ErrorCategory.CONFLICT,
            code,
            "The Actual Start operation mode changed; Preview the required workflow again.",
            correlation_id,
        ))
    fingerprint = fingerprint_payload(
        {
            "mode": "date_only",
            "case_no": facts.case_no,
            "before_actual_start_date": (
                facts.current_actual_start_date.isoformat()
                if facts.current_actual_start_date is not None
                else None
            ),
            "after_actual_start_date": new_date.isoformat(),
            "order_version": facts.order_version,
            "service_data_locked": facts.service_data_locked,
            "has_formal_assignments": facts.has_formal_assignments,
        }
    )
    return ActualStartDateOnlyPreview(
        facts.case_no,
        facts.current_actual_start_date,
        new_date,
        facts.order_version,
        facts.scheduling_version,
        facts.scheduling_generation,
        facts.client_finance_version,
        facts.payroll_version,
        fingerprint,
    )


def _historical_source_context(
    context,
    service_dates,
    source_staff_ids,
    source_assignment_ids=(),
):
    if not service_dates or service_dates != tuple(sorted(set(service_dates))):
        raise ValueError("historical_service_dates_invalid")
    facts = context.shared_facts
    if not source_staff_ids:
        if not facts.scheduling.segments:
            raise ValueError("historical_assignment_required_for_actual_start")
        return ActualStartWorkflowContext(
            replace(
                facts,
                lifecycle=replace(
                    facts.lifecycle,
                    actual_start_date=service_dates[0],
                ),
            ),
            context.reconfirmation,
        )
    if len(source_staff_ids) != 1 or source_staff_ids[0] <= 0:
        raise ValueError("historical_assignment_required_for_actual_start")
    if source_assignment_ids and len(source_assignment_ids) != len(source_staff_ids):
        raise ValueError("historical_assignment_required_for_actual_start")
    # When the planner has already bridged the generation-less historical
    # assignment into an effective generation, retain that formal assignment
    # identity for canonical Scheduling replacement.  Preview-only contexts
    # have no assignment identity yet and use a stable synthetic identity.
    persisted_source_assignment_id = (
        source_assignment_ids[0] if source_assignment_ids else None
    )
    source_assignment_id = (
        facts.scheduling.segments[0].assignment_id
        if len(facts.scheduling.segments) == 1
        else persisted_source_assignment_id or 1
    )
    if persisted_source_assignment_id is not None and persisted_source_assignment_id <= 0:
        raise ValueError("historical_assignment_required_for_actual_start")
    segment = EffectiveAssignmentSegment(
        assignment_id=source_assignment_id,
        staff_id=source_staff_ids[0],
        sequence=1,
        service_day_count=len(service_dates),
        assigned_start_date=service_dates[0],
        assigned_end_date=service_dates[-1],
        official_service_dates=service_dates,
    )
    synthetic_facts = replace(
        facts,
        scheduling=replace(
            facts.scheduling,
            segments=(segment,),
            service_started=False,
        ),
        planned_service_dates=service_dates,
        # The synthetic assignment is the asserted historical Actual Start.
        # Actual Start validates the first assignment against the current
        # Scheduling root, so this preview-only snapshot must project that
        # same asserted root instead of retaining the HCM planned date.
        lifecycle=replace(facts.lifecycle, actual_start_date=service_dates[0]),
    )
    # Historical evidence may retain an assignment identity from a retired
    # generation. Only assignments present in current Scheduling facts may be
    # cancelled or used as replacement lineage. A tombstone has no current
    # assignments even when its evidence still names an old id.
    unpersisted = () if facts.scheduling.segments else (source_assignment_id,)
    return ActualStartWorkflowContext(
        synthetic_facts,
        context.reconfirmation,
        unpersisted_source_assignment_ids=unpersisted,
    )


def _raise_missing_receipt(request):
    raise _workflow_error(request, ErrorCategory.INTERNAL, "idempotency_evidence_incomplete", "The command claim exists without its receipt.")


def _actual_start_lifecycle(facts, new_date, scheduling, client_settlement, clock):
    roots = replace(facts.lifecycle, actual_start_date=new_date, actual_start_reconfirmed=True)
    return build_terms_lifecycle_impact(
        roots,
        facts.order.terms,
        scheduling,
        client_settlement,
        clock.now(),
    )


def _persist_scheduling(repository, request, preview, command_fingerprint):
    candidate = _scheduling_persistence_candidate(preview)
    command = SchedulingReplacementCommand(
        candidate=candidate,
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


def _scheduling_persistence_candidate(preview):
    unpersisted = set(preview.unpersisted_source_assignment_ids)
    if not unpersisted:
        return preview.scheduling
    assignments = tuple(
        replace(
            assignment,
            source_assignment_id=None,
            lineage_source_assignment_ids=(),
        )
        if assignment.source_assignment_id in unpersisted
        else assignment
        for assignment in preview.scheduling.assignments
    )
    return replace(
        preview.scheduling,
        cancelled_assignment_ids=tuple(
            assignment_id
            for assignment_id in preview.scheduling.cancelled_assignment_ids
            if assignment_id not in unpersisted
        ),
        assignments=assignments,
    )


def _persist_lifecycle(repository, request, preview, receipt):
    command = LifecycleImpactPersistenceCommand(
        candidate=preview.lifecycle_impact,
        expected_order_version=preview.order_version,
        resulting_order_version=receipt.order_version,
        client_settlement_fingerprint=preview.client_settlement.fingerprint,
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
            preview.lifecycle_impact.after_status,
            preview.order_version,
            receipt.order_version,
        )
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


def _existing_client_settlement(facts):
    """Read the existing deposit gate without recalculating any amount."""
    client_source = facts.client_finance
    existing = {
        item.payment_stage: item
        for item in client_source.existing_obligations
    }
    deposit = existing.get(PaymentStage.DEPOSIT)
    deposit_settled = (
        client_source.deposit_gate_override_active
        or (
            deposit is None
            and client_source.payment_terms.deposit_service_days == 0
        )
        or (
            deposit is not None
            and deposit.formal_history_exists
            and deposit.net_settled_amount.amount >= deposit.contracted_amount.amount
        )
    )
    all_settled = (
        client_source.open_nonstage_obligation_count == 0
        and all(
            item.formal_history_exists
            and item.net_settled_amount.amount >= item.contracted_amount.amount
            for item in existing.values()
        )
    )
    payload = {
        "mode": "actual_start_existing_settlement",
        "case_no": client_source.case_no,
        "deposit_settled": deposit_settled,
        "all_formal_obligations_settled": all_settled,
    }
    return ClientSettlementProjection(
        deposit_settled,
        all_settled,
        fingerprint_payload(payload),
    )


def _preview_result(
    facts,
    actual_start,
    scheduling,
    client_settlement,
    lifecycle,
    reconfirmation,
    unpersisted_source_assignment_ids,
):
    payload = _preview_fingerprint_payload(
        facts,
        actual_start,
        client_settlement,
        lifecycle,
        reconfirmation,
    )
    return ActualStartPreview(
        facts.lifecycle.actual_start_date,
        actual_start.new_actual_start_date,
        actual_start,
        scheduling,
        facts.order.version,
        facts.scheduling.aggregate_version,
        facts.scheduling.generation_number,
        facts.client_finance.account_version,
        facts.payroll.payroll_version,
        client_settlement,
        lifecycle,
        reconfirmation,
        unpersisted_source_assignment_ids,
        fingerprint_payload(payload),
    )


def _preview_fingerprint_payload(
    facts,
    actual_start,
    client_settlement,
    lifecycle,
    reconfirmation,
):
    return {
        "actual_start": actual_start.fingerprint.value,
        "client_settlement": client_settlement.fingerprint.value,
        "lifecycle": lifecycle.fingerprint.value,
        "reconfirmation": reconfirmation.fingerprint.value,
        "order_version": facts.order.version,
        "scheduling_version": facts.scheduling.aggregate_version,
    }


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


def _build_receipt(preview):
    assignments = preview.scheduling.assignments
    return OrderTermsReceipt(preview.scheduling.case_no, preview.order_version + 1, preview.scheduling.resulting_aggregate_version, preview.scheduling.generation_number, preview.client_finance_version, preview.payroll_version, preview.lifecycle_impact.after_status, preview.lifecycle_impact.service_data_lock_should_exist and not preview.lifecycle_impact.service_data_lock_was_present, preview.scheduling.cancelled_assignment_ids, tuple(item.candidate_key for item in assignments), sum(len(item.service_dates) for item in assignments), sum(item.actual_hours for item in assignments), preview.fingerprint)


def _validate_versions(request, facts):
    for expected, current, domain in _version_comparisons(request, facts):
        _validate_version(request, expected, current, domain)


def _version_comparisons(request, facts):
    return ((request.expected_order_version.value, facts.order.version, "order"), (request.expected_scheduling_version.value, facts.scheduling.aggregate_version, "scheduling"))


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


def _command_fingerprint(request):
    return fingerprint_payload({"case_no": request.case_no, "new_actual_start_date": request.new_actual_start_date.isoformat(), "order_version": request.expected_order_version.value, "scheduling_version": request.expected_scheduling_version.value, "preview_fingerprint": request.preview_fingerprint.value, "actor": request.actor.actor_id, "reason": request.reason})


def _matched_receipt(request, command_fingerprint, stored):
    if stored.command_fingerprint == command_fingerprint:
        return stored.receipt
    raise _workflow_error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_mismatch", "Idempotency key was already used with a different command.")


def _workflow_error(request, category, code, message, *, current_version=None):
    return ActualStartWorkflowError(
        TypedError(
            category,
            code,
            message,
            request.correlation_id,
            current_version=(
                ExpectedVersion(current_version)
                if current_version is not None
                else None
            ),
        )
    )


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
    "HistoricalActualStartSourceAssignment",
]

"""Typed Preview and atomic Apply workflow for leave/substitution batches."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Callable, Protocol

from domains.scheduling.leave_substitution import LeaveSubstitutionBatchIntent, LeaveSubstitutionCandidate, LeaveSubstitutionDomainError, LeaveSubstitutionFacts, LeaveSubstitutionIssue, build_leave_substitution_candidate
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text
from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanPersistenceContext, AssignmentPlanWorkflowFacts, VersionedImpactCandidate
from subsystems.scheduling.holiday_calendar_query import (
    HolidayCalendarFacts,
    HolidayCalendarUnavailable,
    SchedulingHolidayQuery,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_REASON_MAXIMUM_LENGTH = 500


@dataclass(frozen=True, slots=True)
class LeaveSubstitutionWorkflowFacts:
    impact_facts: AssignmentPlanWorkflowFacts | None
    official_schedules: tuple
    preview_blockers: tuple[str, ...] = ()
    scheduling_facts: LeaveSubstitutionFacts | None = None

    @property
    def leave_facts(self) -> LeaveSubstitutionFacts:
        if self.scheduling_facts is not None:
            return self.scheduling_facts
        if self.impact_facts is None:
            raise ValueError("leave_preview_facts_missing")
        return LeaveSubstitutionFacts(self.impact_facts.assignment_plan, self.official_schedules, self.impact_facts.lifecycle.service_data_locked)


@dataclass(frozen=True, slots=True)
class LeaveSubstitutionPreviewRequest:
    case_no: str
    intent: LeaveSubstitutionBatchIntent
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_case_number(self.case_no)


@dataclass(frozen=True, slots=True)
class LeaveSubstitutionApplyRequest:
    case_no: str; intent: LeaveSubstitutionBatchIntent; expected_order_version: ExpectedVersion; expected_scheduling_version: ExpectedVersion
    expected_client_finance_version: ExpectedVersion; expected_payroll_version: ExpectedVersion; preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey; actor: ActorContext; reason: str; correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_case_number(self.case_no)
        require_canonical_text(self.reason, "leave/substitution reason", _REASON_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class LeaveSubstitutionPreview:
    candidate: LeaveSubstitutionCandidate; client_finance_impact: VersionedImpactCandidate; payroll_impact: VersionedImpactCandidate; orders_impact: VersionedImpactCandidate
    order_version: int; scheduling_version: int; client_finance_version: int; payroll_version: int; fingerprint: PreviewFingerprint
    calendar_candidate: "LeaveCalendarCandidate"; apply_readiness: "LeaveApplyReadiness"


@dataclass(frozen=True, slots=True)
class LeaveCalendarDay:
    calendar_date: str; before_kind: str; after_kind: str; change_kind: str
    before_staff_id: int | None; after_staff_id: int | None


@dataclass(frozen=True, slots=True)
class LeaveCalendarCandidate:
    before_service_day_count: int; after_service_day_count: int
    before_service_start_date: str | None; before_service_end_date: str | None
    after_service_start_date: str | None; after_service_end_date: str | None
    contracted_service_day_count: int; deferred_day_count: int; substitute_day_count: int; leave_day_count: int
    holiday_rest_day_count: int; fixed_rest_day_count: int; holiday_version: str; holiday_rows: tuple[tuple[str, str], ...]
    conservation_status: str; day_cells: tuple[LeaveCalendarDay, ...]


@dataclass(frozen=True, slots=True)
class LeaveApplyReadiness:
    status: str; blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BlockedLeaveImpact:
    expected_version: int
    resulting_version: int
    fingerprint: PreviewFingerprint
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LeaveSubstitutionReceipt:
    batch_key: str; case_no: str; order_version: int; scheduling_generation: int; scheduling_version: int
    client_finance_version: int; payroll_version: int; outcome_event_ids: tuple[int, ...]; preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class LeaveBatchHeaderEvidence:
    batch_key: str; case_no: str; command_fingerprint: PreviewFingerprint; preview_fingerprint: PreviewFingerprint
    item_count: int; actor: str; reason: str; request_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class LeaveOutcomeEvidence:
    outcome_event_id: int; item_index: int; original_assignment_id: int; original_schedule_id: int
    work_date: str; resolution_type: str; result_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredLeaveSubstitutionReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: LeaveSubstitutionReceipt


@dataclass(frozen=True, slots=True)
class LeaveApplyEvidence:
    facts: LeaveSubstitutionWorkflowFacts; claim_state: "CommandClaimState"; header: LeaveBatchHeaderEvidence | None
    outcomes: tuple[LeaveOutcomeEvidence, ...]; receipt: StoredLeaveSubstitutionReceipt | None


class CommandClaimState(Enum):
    CREATED = "created"; MATCHED = "matched"; MISMATCH = "mismatch"


class LeaveSubstitutionRepository(Protocol):
    def load_for_preview(self, case_no: str, intent: LeaveSubstitutionBatchIntent) -> LeaveSubstitutionWorkflowFacts: ...
    def preflight_impacted_staff_ids(self, case_no: str, intent: LeaveSubstitutionBatchIntent) -> tuple[int, ...]: ...
    def load_for_apply(self, request: LeaveSubstitutionApplyRequest, preflight_staff_ids: tuple[int, ...], command_fingerprint: PreviewFingerprint) -> LeaveApplyEvidence: ...
    def replace_scheduling_generation(self, candidate, context: AssignmentPlanPersistenceContext) -> object: ...
    def append_batch_outcomes(self, request, preview, command_fingerprint, scheduling_result) -> tuple[int, ...]: ...
    def save_receipt(self, stored: StoredLeaveSubstitutionReceipt, scheduling_result: object, context: AssignmentPlanPersistenceContext) -> None: ...


class LeaveClientFinanceImpactPort(Protocol):
    def preview_leave_substitution(self, facts: AssignmentPlanWorkflowFacts, scheduling) -> VersionedImpactCandidate: ...
    def persist_leave_substitution(self, candidate: VersionedImpactCandidate, context: AssignmentPlanPersistenceContext, scheduling_result: object) -> None: ...


class LeavePayrollImpactPort(LeaveClientFinanceImpactPort, Protocol): pass


class LeaveOrdersImpactPort(Protocol):
    def preview_leave_substitution(self, facts: AssignmentPlanWorkflowFacts, scheduling, client_finance: VersionedImpactCandidate) -> VersionedImpactCandidate: ...
    def persist_leave_substitution(self, candidate: VersionedImpactCandidate, context: AssignmentPlanPersistenceContext, scheduling_result: object) -> None: ...


class LeaveSubstitutionWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message); self.error = error


class LeaveSubstitutionWorkflow:
    def __init__(self, repository: LeaveSubstitutionRepository, client_finance_port: LeaveClientFinanceImpactPort, payroll_port: LeavePayrollImpactPort, orders_port: LeaveOrdersImpactPort, holiday_query: SchedulingHolidayQuery, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository; self._client_finance_port = client_finance_port; self._payroll_port = payroll_port; self._orders_port = orders_port; self._holiday_query = holiday_query; self._unit_of_work_factory = unit_of_work_factory

    def preview(self, request: LeaveSubstitutionPreviewRequest) -> LeaveSubstitutionPreview:
        return self._build_preview(self._repository.load_for_preview(request.case_no, request.intent), request.intent, request.correlation_id, lock_holidays=False)

    def apply(self, request: LeaveSubstitutionApplyRequest) -> LeaveSubstitutionReceipt:
        try: return self._apply_transaction(request)
        except LeaveSubstitutionWorkflowError: raise
        except Exception as exception: raise _workflow_error(request.correlation_id, ErrorCategory.INTERNAL, "transaction_failed", "The leave/substitution transaction failed and was rolled back.") from exception

    def _apply_transaction(self, request):
        command_fingerprint = _command_fingerprint(request); preflight = _canonical_staff_ids(self._repository.preflight_impacted_staff_ids(request.case_no, request.intent))
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self._replay_or_apply(request, command_fingerprint, preflight); unit_of_work.commit(); return receipt

    def _replay_or_apply(self, request, command_fingerprint, preflight):
        evidence = self._repository.load_for_apply(request, preflight, command_fingerprint); _raise_if_claim_mismatched(request, evidence.claim_state)
        replay = _validate_replay_evidence(request, command_fingerprint, evidence.claim_state, evidence)
        return replay if replay is not None else self._apply_fresh(request, command_fingerprint, preflight, evidence.facts)

    def _apply_fresh(self, request, command_fingerprint, preflight, facts):
        _validate_locked_staff_set(request, facts, preflight); _validate_expected_versions(request, facts.leave_facts)
        preview = self._build_preview(facts, request.intent, request.correlation_id, lock_holidays=True); _validate_preview_fingerprint(request, preview)
        _raise_if_impacts_blocked(request.correlation_id, preview.client_finance_impact, preview.payroll_impact, preview.orders_impact)
        return self._persist(request, preview, command_fingerprint)

    def _build_preview(self, facts, intent, correlation_id, *, lock_holidays):
        try:
            holiday_facts = _query_holiday_facts(
                facts.leave_facts,
                intent,
                self._holiday_query,
                lock_holidays,
            )
        except HolidayCalendarUnavailable as error:
            raise _workflow_error(
                correlation_id,
                ErrorCategory.UNAVAILABLE,
                "holiday_calendar_unavailable",
                "The canonical holiday calendar is unavailable.",
            ) from error
        candidate = _build_domain_candidate(
            facts,
            intent,
            correlation_id,
            tuple(item.holiday_date for item in holiday_facts.holidays),
        )
        calendar_candidate = _calendar_candidate(
            facts.leave_facts,
            candidate,
            holiday_facts,
        )
        client_finance, payroll, orders = self._build_impacts(facts, candidate, correlation_id)
        return _preview_result(facts.leave_facts, candidate, client_finance, payroll, orders, calendar_candidate)

    def _build_impacts(self, facts, candidate, correlation_id):
        if facts.impact_facts is None:
            blocked = tuple(_blocked_impact(code) for code in facts.preview_blockers)
            return blocked[0], blocked[0], blocked[0]
        client_finance = _preview_impact(
            lambda: self._client_finance_port.preview_leave_substitution(
                facts.impact_facts,
                candidate.scheduling,
            )
        )
        payroll = _preview_impact(
            lambda: self._payroll_port.preview_leave_substitution(
                facts.impact_facts,
                candidate.scheduling,
            )
        )
        orders = _preview_impact(
            lambda: self._orders_port.preview_leave_substitution(
                facts.impact_facts,
                candidate.scheduling,
                client_finance,
            )
        )
        return client_finance, payroll, orders

    def _persist(self, request, preview, command_fingerprint):
        context = AssignmentPlanPersistenceContext(request.idempotency_key, request.actor, request.reason, request.correlation_id, preview.fingerprint, command_fingerprint, preview.order_version, ())
        scheduling_result = self._repository.replace_scheduling_generation(preview.candidate.scheduling, context)
        event_ids = self._repository.append_batch_outcomes(request, preview, command_fingerprint, scheduling_result)
        self._client_finance_port.persist_leave_substitution(preview.client_finance_impact, context, scheduling_result)
        self._payroll_port.persist_leave_substitution(preview.payroll_impact, context, scheduling_result)
        self._orders_port.persist_leave_substitution(preview.orders_impact, context, scheduling_result)
        receipt = _build_receipt(request, preview, event_ids)
        self._repository.save_receipt(StoredLeaveSubstitutionReceipt(command_fingerprint, receipt), scheduling_result, context)
        return receipt


def _build_domain_candidate(facts, intent, correlation_id, holiday_rest_dates=()):
    try: return build_leave_substitution_candidate(facts.leave_facts, intent, holiday_rest_dates)
    except LeaveSubstitutionDomainError as exception: raise _domain_workflow_error(correlation_id, exception) from exception
def _preview_result(facts, candidate, client_finance, payroll, orders, calendar_candidate):
    blockers = tuple(sorted(set(item for impact in (client_finance, payroll, orders) for item in impact.blockers)))
    return LeaveSubstitutionPreview(candidate, client_finance, payroll, orders, facts.assignment_plan.order_version, facts.assignment_plan.scheduling_version, facts.assignment_plan.client_finance_version, facts.assignment_plan.payroll_version, fingerprint_payload({"leave":candidate.fingerprint.value,"client_finance":client_finance.fingerprint.value,"payroll":payroll.fingerprint.value,"orders":orders.fingerprint.value,"holiday_version":calendar_candidate.holiday_version}), calendar_candidate, LeaveApplyReadiness("blocked" if blockers else "ready", blockers))


def _blocked_impact(blocker):
    return BlockedLeaveImpact(
        0,
        0,
        fingerprint_payload({"leave_preview_blocker": blocker}),
        (blocker,),
    )


def _calendar_candidate(facts, candidate, holiday_facts):
    before = {item.work_date: item.staff_id for item in facts.official_schedules}
    after = {service_date: assignment.staff_id for assignment in candidate.scheduling.assignments for service_date in assignment.service_dates}
    outcomes = {item.original_work_date: item for item in candidate.outcomes}
    cells = []
    for calendar_date in sorted(set(before) | set(after)):
        outcome = outcomes.get(calendar_date)
        change = "unchanged"
        if outcome is not None:
            change = "substitute" if outcome.resolution_type.value == "substitute" else "deferred_from"
        elif calendar_date not in before:
            change = "deferred_to"
        cells.append(LeaveCalendarDay(calendar_date.isoformat(), "service" if calendar_date in before else "none", "service" if calendar_date in after else "none", change, before.get(calendar_date), after.get(calendar_date)))
    service_dates = tuple(sorted(set(before) | set(after)))
    holidays = tuple(
        item
        for item in holiday_facts.holidays
        if min(service_dates) <= item.holiday_date <= max(service_dates)
    )
    outcomes_by_type = tuple(item.resolution_type.value for item in candidate.outcomes)
    return LeaveCalendarCandidate(
        len(before),
        len(after),
        _calendar_boundary(before, min),
        _calendar_boundary(before, max),
        _calendar_boundary(after, min),
        _calendar_boundary(after, max),
        facts.assignment_plan.contracted_service_days,
        outcomes_by_type.count("defer_following_assignments"),
        outcomes_by_type.count("substitute"),
        len(candidate.outcomes),
        len(holidays),
        0,
        holiday_facts.holiday_version,
        tuple((item.holiday_date.isoformat(), item.holiday_name) for item in holidays),
        "conserved" if len(before) == len(after) else "failed",
        tuple(cells),
    )


def _query_holiday_facts(facts, intent, holiday_query, lock_holidays):
    service_dates = tuple(item.work_date for item in facts.official_schedules)
    if not service_dates:
        raise HolidayCalendarUnavailable("service dates are missing")
    service_horizon = facts.assignment_plan.contracted_service_days + len(intent.items)
    return holiday_query.query(
        min(service_dates),
        max(service_dates) + timedelta(days=service_horizon),
        lock=lock_holidays,
    )


def _calendar_boundary(service_days, reducer):
    return None if not service_days else reducer(service_days).isoformat()


def _preview_impact(build_impact):
    try:
        return build_impact()
    except ValueError as exception:
        code = str(exception) or "leave_substitution_impact_invalid"
        return BlockedLeaveImpact(
            0,
            0,
            fingerprint_payload({"blocked_impact": code}),
            (code,),
        )
def _build_receipt(request, preview, event_ids):
    scheduling = preview.candidate.scheduling; return LeaveSubstitutionReceipt(request.idempotency_key.value, request.case_no, preview.orders_impact.resulting_version, scheduling.generation_number, scheduling.resulting_aggregate_version, preview.client_finance_impact.resulting_version, preview.payroll_impact.resulting_version, event_ids, preview.fingerprint)
def _validate_replay_evidence(request, command_fingerprint, claim, evidence):
    parts = (evidence.header is not None, evidence.receipt is not None)
    if claim is CommandClaimState.CREATED:
        if any(parts) or evidence.outcomes: _raise_replay_integrity(request, "batch evidence exists without its claim")
        return None
    if not all(parts): _raise_replay_integrity(request, "batch replay evidence is incomplete")
    _validate_header_identity(request, command_fingerprint, evidence.header); _validate_outcome_evidence(request, evidence.header, evidence.outcomes); _validate_receipt_outcomes(request, evidence)
    if evidence.receipt.command_fingerprint != command_fingerprint: raise _workflow_error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "batch_key_request_identity_conflict", "Batch key was already used with a different request identity.")
    return evidence.receipt.receipt
def _validate_header_identity(request, command_fingerprint, header):
    matches = (header.batch_key == request.idempotency_key.value and header.case_no == request.case_no and header.command_fingerprint == command_fingerprint and header.preview_fingerprint == request.preview_fingerprint and header.item_count == len(request.intent.items) and header.actor == request.actor.actor_id and header.reason == request.reason and header.request_fingerprint == leave_request_fingerprint(request.intent))
    if not matches: raise _workflow_error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "batch_key_request_identity_conflict", "Batch key was already used with different request, actor, or reason.")
def _validate_outcome_evidence(request, header, outcomes):
    if len(outcomes) != header.item_count: _raise_replay_integrity(request, "batch outcome count is invalid")
    if tuple(item.item_index for item in outcomes) != tuple(range(header.item_count)): _raise_replay_integrity(request, "batch outcome ordinals are invalid")
    for item, outcome in zip(request.intent.items, outcomes):
        if not _outcome_identity_matches(request, item, outcome): _raise_replay_integrity(request, "batch outcome lineage is invalid")
def _validate_receipt_outcomes(request, evidence):
    if evidence.receipt.receipt.outcome_event_ids != tuple(item.outcome_event_id for item in evidence.outcomes): _raise_replay_integrity(request, "receipt outcome lineage is invalid")
def _outcome_identity_matches(request, item, outcome): return outcome.original_assignment_id == request.intent.original_assignment_id and outcome.original_schedule_id == item.original_schedule_id and outcome.work_date == item.work_date.isoformat() and outcome.resolution_type == item.resolution_type.value
def _validate_locked_staff_set(request, facts, preflight):
    fresh = {item.staff_id for item in facts.leave_facts.assignment_plan.effective_assignments}; fresh.update(item.substitute_staff_id for item in request.intent.items if item.substitute_staff_id is not None)
    if tuple(sorted(fresh)) != preflight: raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "scheduling_lock_set_stale", "Impacted caregiver set changed after preflight.")
def _validate_expected_versions(request, facts):
    plan = facts.assignment_plan; expected = (request.expected_order_version.value,request.expected_scheduling_version.value,request.expected_client_finance_version.value,request.expected_payroll_version.value); current = (plan.order_version,plan.scheduling_version,plan.client_finance_version,plan.payroll_version)
    if expected != current: raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_version", "Leave/substitution source versions changed after Preview.")
def _validate_preview_fingerprint(request, preview):
    if request.preview_fingerprint != preview.fingerprint: raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_preview", "Leave/substitution facts changed after Preview.")
def _raise_if_impacts_blocked(correlation_id, *impacts):
    blockers = tuple(item for impact in impacts for item in impact.blockers)
    if blockers: raise LeaveSubstitutionWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, "leave_substitution_domain_blocked", "Leave/substitution requires human review before Apply.", correlation_id, domain_blockers=tuple(sorted(set(blockers)))))
def _raise_if_claim_mismatched(request, claim):
    if claim is CommandClaimState.MISMATCH: raise _workflow_error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "batch_key_request_identity_conflict", "Batch key was already used with a different command.")
def _raise_replay_integrity(request, message): raise _workflow_error(request.correlation_id, ErrorCategory.DOMAIN_BLOCKED, "invalid_batch_replay_snapshot", message)
def _command_fingerprint(request): return fingerprint_payload({"family":"scheduling-leave-substitution","batch_key":request.idempotency_key.value,"case_no":request.case_no,"request_fingerprint":leave_request_fingerprint(request.intent).value,"expected_versions":{"order":request.expected_order_version.value,"scheduling":request.expected_scheduling_version.value,"client_finance":request.expected_client_finance_version.value,"payroll":request.expected_payroll_version.value},"preview_fingerprint":request.preview_fingerprint.value,"actor":request.actor.actor_id,"reason":request.reason})
def leave_request_fingerprint(intent): return fingerprint_payload({"original_assignment_id":intent.original_assignment_id,"items":tuple({"original_schedule_id":item.original_schedule_id,"work_date":item.work_date.isoformat(),"resolution_type":item.resolution_type.value,"substitute_staff_id":item.substitute_staff_id,"is_double_pay":item.is_double_pay} for item in intent.items)})
def _domain_workflow_error(correlation_id, exception):
    categories = {LeaveSubstitutionIssue.INVALID_INTENT:ErrorCategory.VALIDATION,LeaveSubstitutionIssue.ASSIGNMENT_NOT_FOUND:ErrorCategory.NOT_FOUND}; return _workflow_error(correlation_id,categories.get(exception.issue,ErrorCategory.DOMAIN_BLOCKED),exception.issue.value,str(exception))
def _impact_workflow_error(correlation_id, exception):
    code = str(exception) or "leave_substitution_impact_invalid"; return LeaveSubstitutionWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED,code,"A dependent Domain rejected the leave/substitution impact.",correlation_id,domain_blockers=(code,)))
def _workflow_error(correlation_id, category, code, message): return LeaveSubstitutionWorkflowError(TypedError(category,code,message,correlation_id))
def _validate_case_number(case_no): require_canonical_text(case_no,"case number",_CASE_NUMBER_MAXIMUM_LENGTH)
def _canonical_staff_ids(staff_ids):
    canonical = tuple(sorted(set(staff_ids)))
    if canonical != staff_ids or not canonical: raise ValueError("scheduling impacted staff ids must be canonical")
    if any(isinstance(value,bool) or not isinstance(value,int) or value <= 0 for value in canonical): raise ValueError("scheduling impacted staff ids must be positive integers")
    return canonical

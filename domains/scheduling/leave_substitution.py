"""Pure multi-day leave and substitution planning for Scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from domains.scheduling.assignment_plan import (
    AssignmentPlanFacts,
    StaffOccupancyFact,
)
from domains.scheduling.generation import (
    AssignmentCandidate,
    BufferCandidate,
    SchedulingGenerationCandidate,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_positive_integer


_BUFFER_DAY_COUNT = 7
_MAXIMUM_EFFECTIVE_ASSIGNMENTS = 4


class LeaveResolutionType(StrEnum):
    DEFER_FOLLOWING_ASSIGNMENTS = "defer_following_assignments"
    SUBSTITUTE = "substitute"


class LeaveSubstitutionIssue(StrEnum):
    INVALID_INTENT = "invalid_scheduling_intent"
    SERVICE_DATA_LOCKED = "service_data_locked"
    ASSIGNMENT_NOT_FOUND = "assignment_not_found"
    SERVICE_OWNERSHIP_CONFLICT = "service_ownership_conflict"
    COVERAGE_INCOMPLETE = "coverage_incomplete"
    STAFF_OCCUPANCY_CONFLICT = "staff_occupancy_conflict"
    ASSIGNMENT_LIMIT_EXCEEDED = "assignment_limit_exceeded"


class LeaveSubstitutionDomainError(ValueError):
    def __init__(self, issue: LeaveSubstitutionIssue, message: str) -> None:
        super().__init__(message)
        self.issue = issue


@dataclass(frozen=True, slots=True)
class OfficialScheduleFact:
    schedule_id: int
    assignment_id: int
    staff_id: int
    work_date: date
    is_double_pay: bool = False

    def __post_init__(self) -> None:
        require_positive_integer(self.schedule_id, "schedule id")
        require_positive_integer(self.assignment_id, "assignment id")
        require_positive_integer(self.staff_id, "staff id")
        _require_date(self.work_date, "work date")
        if not isinstance(self.is_double_pay, bool):
            raise TypeError("double-pay marker must be bool")


@dataclass(frozen=True, slots=True)
class LeaveSubstitutionItem:
    original_schedule_id: int
    work_date: date
    resolution_type: LeaveResolutionType
    substitute_staff_id: int | None = None
    is_double_pay: bool = False

    def __post_init__(self) -> None:
        require_positive_integer(self.original_schedule_id, "original schedule id")
        _require_date(self.work_date, "leave work date")
        _validate_resolution(self)


@dataclass(frozen=True, slots=True)
class LeaveSubstitutionBatchIntent:
    original_assignment_id: int
    items: tuple[LeaveSubstitutionItem, ...]

    def __post_init__(self) -> None:
        require_positive_integer(
            self.original_assignment_id,
            "original assignment id",
        )
        _validate_batch_items(self.items)


@dataclass(frozen=True, slots=True)
class LeaveSubstitutionFacts:
    assignment_plan: AssignmentPlanFacts
    official_schedules: tuple[OfficialScheduleFact, ...]
    service_data_locked: bool

    def __post_init__(self) -> None:
        if not isinstance(self.official_schedules, tuple):
            raise TypeError("official schedules must be a tuple")
        if not isinstance(self.service_data_locked, bool):
            raise TypeError("service-data lock marker must be bool")
        _validate_schedule_facts(self)


@dataclass(frozen=True, slots=True)
class LeaveOutcomeCandidate:
    item_index: int
    original_schedule_id: int
    original_assignment_id: int
    original_staff_id: int
    original_work_date: date
    resolution_type: LeaveResolutionType
    leave_occupancy_date: date
    resulting_service_date: date
    resulting_staff_id: int
    resulting_assignment_key: str
    is_double_pay: bool


@dataclass(frozen=True, slots=True)
class LeaveSubstitutionCandidate:
    scheduling: SchedulingGenerationCandidate
    outcomes: tuple[LeaveOutcomeCandidate, ...]
    impacted_staff_ids: tuple[int, ...]
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class _ServiceOwner:
    service_date: date
    staff_id: int
    source_assignment_id: int
    source_schedule_id: int
    is_double_pay: bool


# The invariant order is visible here so validation cannot drift between callers.
def build_leave_substitution_candidate(
    facts: LeaveSubstitutionFacts,
    intent: LeaveSubstitutionBatchIntent,
) -> LeaveSubstitutionCandidate:
    if facts.service_data_locked:
        raise LeaveSubstitutionDomainError(
            LeaveSubstitutionIssue.SERVICE_DATA_LOCKED,
            "service data is permanently locked",
        )
    selected = _selected_schedule_facts(facts, intent)
    transformed = _transform_service_ownership(facts, intent, selected)
    assignments = _build_assignments(facts, intent, transformed)
    buffers = _build_buffers(assignments, facts.assignment_plan.service_started)
    _validate_external_occupancy(
        facts.assignment_plan.case_no,
        facts.assignment_plan.external_occupancy,
        assignments,
        buffers,
        _leave_occupancy_keys(intent, selected),
    )
    scheduling = _build_generation(facts.assignment_plan, assignments, buffers)
    outcomes = _build_outcomes(intent, selected, transformed, assignments)
    fingerprint = fingerprint_payload(
        _candidate_payload(facts, intent, scheduling, outcomes)
    )
    return LeaveSubstitutionCandidate(
        scheduling=scheduling,
        outcomes=outcomes,
        impacted_staff_ids=_impacted_staff_ids(facts, intent),
        fingerprint=fingerprint,
    )


def _validate_resolution(item: LeaveSubstitutionItem) -> None:
    if not isinstance(item.resolution_type, LeaveResolutionType):
        raise TypeError("leave resolution type is invalid")
    if not isinstance(item.is_double_pay, bool):
        raise TypeError("double-pay marker must be bool")
    if item.resolution_type is LeaveResolutionType.SUBSTITUTE:
        require_positive_integer(item.substitute_staff_id, "substitute staff id")
        return
    if item.substitute_staff_id is not None:
        _raise_invalid("deferred leave cannot specify substitute staff")
    if item.is_double_pay:
        _raise_invalid("deferred leave cannot create a double-pay event")


def _validate_batch_items(items: tuple[LeaveSubstitutionItem, ...]) -> None:
    if not isinstance(items, tuple) or not items:
        _raise_invalid("leave batch requires at least one item")
    if any(not isinstance(item, LeaveSubstitutionItem) for item in items):
        raise TypeError("leave batch contains an invalid item")
    ordered = tuple(sorted(items, key=lambda item: (item.work_date, item.original_schedule_id)))
    if items != ordered:
        _raise_invalid("leave batch items must be canonically ordered")
    schedule_ids = tuple(item.original_schedule_id for item in items)
    work_dates = tuple(item.work_date for item in items)
    if len(schedule_ids) != len(set(schedule_ids)):
        _raise_invalid("leave batch repeats an original schedule")
    if len(work_dates) != len(set(work_dates)):
        _raise_invalid("leave batch repeats a work date")


def _validate_schedule_facts(facts: LeaveSubstitutionFacts) -> None:
    schedules = facts.official_schedules
    if any(not isinstance(item, OfficialScheduleFact) for item in schedules):
        raise TypeError("official schedules contain an invalid value")
    ordered = tuple(sorted(schedules, key=lambda item: (item.work_date, item.schedule_id)))
    if schedules != ordered:
        raise ValueError("official schedules must be canonically ordered")
    if len({item.schedule_id for item in schedules}) != len(schedules):
        raise ValueError("official schedule identity is duplicated")
    if len({item.work_date for item in schedules}) != len(schedules):
        _raise_ownership("one service date has multiple official owners")
    expected_days = facts.assignment_plan.contracted_service_days
    if len(schedules) != expected_days:
        _raise_coverage("official service days do not conserve the contract")
    _validate_schedule_assignment_ownership(facts)


def _validate_schedule_assignment_ownership(facts: LeaveSubstitutionFacts) -> None:
    assignments = {
        item.assignment_id: item
        for item in facts.assignment_plan.effective_assignments
    }
    for schedule in facts.official_schedules:
        assignment = assignments.get(schedule.assignment_id)
        if assignment is None or assignment.staff_id != schedule.staff_id:
            _raise_ownership("official schedule owner is not effective")
        if schedule.work_date not in assignment.official_service_dates:
            _raise_ownership("official schedule date is absent from its assignment")


def _selected_schedule_facts(
    facts: LeaveSubstitutionFacts,
    intent: LeaveSubstitutionBatchIntent,
) -> dict[date, OfficialScheduleFact]:
    by_id = {item.schedule_id: item for item in facts.official_schedules}
    selected: dict[date, OfficialScheduleFact] = {}
    for item in intent.items:
        schedule = by_id.get(item.original_schedule_id)
        if schedule is None or schedule.work_date != item.work_date:
            _raise_ownership("leave item does not match an official schedule")
        if schedule.assignment_id != intent.original_assignment_id:
            _raise_assignment("leave item belongs to another assignment")
        if item.substitute_staff_id == schedule.staff_id:
            _raise_invalid("substitute staff must differ from the original owner")
        selected[item.work_date] = schedule
    return selected


def _transform_service_ownership(
    facts: LeaveSubstitutionFacts,
    intent: LeaveSubstitutionBatchIntent,
    selected: dict[date, OfficialScheduleFact],
) -> tuple[_ServiceOwner, ...]:
    intent_by_date = {item.work_date: item for item in intent.items}
    deferred_dates = tuple(
        item.work_date
        for item in intent.items
        if item.resolution_type is LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS
    )
    transformed = tuple(
        _transform_service_row(row, intent_by_date.get(row.work_date), deferred_dates)
        for row in facts.official_schedules
    )
    _validate_transformed_service_rows(facts, transformed, selected)
    return transformed


# One row owns the defer offset and substitution ownership decision together.
def _transform_service_row(
    row: OfficialScheduleFact,
    item: LeaveSubstitutionItem | None,
    deferred_dates: tuple[date, ...],
) -> _ServiceOwner:
    offset = sum(deferred_date <= row.work_date for deferred_date in deferred_dates)
    resulting_date = row.work_date + timedelta(days=offset)
    if item is None or item.resolution_type is not LeaveResolutionType.SUBSTITUTE:
        return _ServiceOwner(
            resulting_date,
            row.staff_id,
            row.assignment_id,
            row.schedule_id,
            row.is_double_pay,
        )
    return _ServiceOwner(
        resulting_date,
        item.substitute_staff_id,
        row.assignment_id,
        row.schedule_id,
        item.is_double_pay,
    )


def _validate_transformed_service_rows(
    facts: LeaveSubstitutionFacts,
    transformed: tuple[_ServiceOwner, ...],
    selected: dict[date, OfficialScheduleFact],
) -> None:
    del selected
    dates = tuple(item.service_date for item in transformed)
    if dates != tuple(sorted(set(dates))):
        _raise_ownership("leave transition creates duplicate service ownership")
    if len(transformed) != facts.assignment_plan.contracted_service_days:
        _raise_coverage("leave transition changes contracted service quantity")


def _build_assignments(
    facts: LeaveSubstitutionFacts,
    intent: LeaveSubstitutionBatchIntent,
    rows: tuple[_ServiceOwner, ...],
) -> tuple[AssignmentCandidate, ...]:
    assignments = _source_assignment_candidates(facts, intent, rows)
    assignments += _substitute_assignment_candidates(facts, intent, rows)
    ordered = tuple(sorted(assignments, key=_assignment_sort_key))
    if len(ordered) > _MAXIMUM_EFFECTIVE_ASSIGNMENTS:
        raise LeaveSubstitutionDomainError(
            LeaveSubstitutionIssue.ASSIGNMENT_LIMIT_EXCEEDED,
            "leave transition would exceed four effective assignments",
        )
    resequenced = tuple(
        _resequence_assignment(facts.assignment_plan, assignment, index + 1)
        for index, assignment in enumerate(ordered)
    )
    _validate_assignment_intervals(resequenced)
    return resequenced


def _source_assignment_candidates(
    facts: LeaveSubstitutionFacts,
    intent: LeaveSubstitutionBatchIntent,
    rows: tuple[_ServiceOwner, ...],
) -> tuple[AssignmentCandidate, ...]:
    result = []
    for assignment in facts.assignment_plan.effective_assignments:
        assignment_rows = tuple(
            row
            for row in rows
            if row.source_assignment_id == assignment.assignment_id
            and row.staff_id == assignment.staff_id
        )
        if not assignment_rows:
            continue
        result.append(
            _build_source_assignment(facts, intent, assignment, assignment_rows)
        )
    return tuple(result)


# All source-family conservation fields must be constructed from one snapshot.
def _build_source_assignment(
    facts: LeaveSubstitutionFacts,
    intent: LeaveSubstitutionBatchIntent,
    assignment,
    rows: tuple[_ServiceOwner, ...],
) -> AssignmentCandidate:
    if assignment.assigned_start_date is None or assignment.assigned_end_date is None:
        _raise_assignment("effective assignment interval is incomplete")
    deferred_dates = _deferred_dates(intent)
    start_offset = sum(
        value < assignment.assigned_start_date for value in deferred_dates
    )
    end_offset = sum(
        value <= assignment.assigned_end_date for value in deferred_dates
    )
    return AssignmentCandidate(
        candidate_key="pending-sequence",
        source_assignment_id=assignment.assignment_id,
        staff_id=assignment.staff_id,
        sequence=1,
        assigned_start_date=assignment.assigned_start_date + timedelta(days=start_offset),
        assigned_end_date=assignment.assigned_end_date + timedelta(days=end_offset),
        service_dates=tuple(row.service_date for row in rows),
        actual_hours=len(rows) * facts.assignment_plan.service_hours_per_day,
        lineage_source_assignment_ids=(assignment.assignment_id,),
        double_pay_dates=tuple(
            row.service_date for row in rows if row.is_double_pay
        ),
    )


# Substitute rows retain one-to-one schedule lineage while building assignments.
def _substitute_assignment_candidates(
    facts: LeaveSubstitutionFacts,
    intent: LeaveSubstitutionBatchIntent,
    rows: tuple[_ServiceOwner, ...],
) -> tuple[AssignmentCandidate, ...]:
    schedule_by_id = {
        item.schedule_id: item for item in facts.official_schedules
    }
    transformed_by_id = {item.source_schedule_id: item for item in rows}
    result = []
    for item in intent.items:
        if item.resolution_type is not LeaveResolutionType.SUBSTITUTE:
            continue
        source = schedule_by_id[item.original_schedule_id]
        transformed = transformed_by_id[item.original_schedule_id]
        result.append(
            AssignmentCandidate(
                candidate_key="pending-sequence",
                source_assignment_id=source.assignment_id,
                staff_id=item.substitute_staff_id,
                sequence=1,
                assigned_start_date=transformed.service_date,
                assigned_end_date=transformed.service_date,
                service_dates=(transformed.service_date,),
                actual_hours=facts.assignment_plan.service_hours_per_day,
                lineage_source_assignment_ids=(source.assignment_id,),
                double_pay_dates=(
                    (transformed.service_date,) if transformed.is_double_pay else ()
                ),
            )
        )
    return tuple(result)


def _assignment_sort_key(assignment: AssignmentCandidate):
    return (
        assignment.assigned_start_date,
        assignment.service_dates[0],
        assignment.assigned_end_date,
        assignment.staff_id,
    )


def _resequence_assignment(
    facts: AssignmentPlanFacts,
    assignment: AssignmentCandidate,
    sequence: int,
) -> AssignmentCandidate:
    return AssignmentCandidate(
        candidate_key=f"{facts.case_no}:g{facts.scheduling_generation + 1}:a{sequence}",
        source_assignment_id=assignment.source_assignment_id,
        staff_id=assignment.staff_id,
        sequence=sequence,
        assigned_start_date=assignment.assigned_start_date,
        assigned_end_date=assignment.assigned_end_date,
        service_dates=assignment.service_dates,
        actual_hours=assignment.actual_hours,
        lineage_source_assignment_ids=assignment.lineage_source_assignment_ids,
        double_pay_dates=assignment.double_pay_dates,
    )


def _validate_assignment_intervals(
    assignments: tuple[AssignmentCandidate, ...],
) -> None:
    occupied: set[tuple[int, date]] = set()
    for assignment in assignments:
        for occupied_date in _inclusive_dates(
            assignment.assigned_start_date,
            assignment.assigned_end_date,
        ):
            identity = (assignment.staff_id, occupied_date)
            if identity in occupied:
                _raise_occupancy("one caregiver has overlapping assignment intervals")
            occupied.add(identity)


def _build_buffers(
    assignments: tuple[AssignmentCandidate, ...],
    service_started: bool,
) -> tuple[BufferCandidate, ...]:
    return tuple(
        BufferCandidate(
            candidate_key=f"{assignment.candidate_key}:buffer",
            staff_id=assignment.staff_id,
            dates=tuple(
                assignment.assigned_end_date + timedelta(days=offset)
                for offset in range(1, _BUFFER_DAY_COUNT + 1)
            ),
            active=not service_started,
        )
        for assignment in assignments
    )


# Assignment intervals, buffers, and leave days form one occupancy invariant.
def _validate_external_occupancy(
    case_no: str,
    external: tuple[StaffOccupancyFact, ...],
    assignments: tuple[AssignmentCandidate, ...],
    buffers: tuple[BufferCandidate, ...],
    leave_occupancy: set[tuple[int, date]],
) -> None:
    external_keys = {
        (item.staff_id, item.occupancy_date)
        for item in external
        if item.source_case_no != case_no
    }
    proposed = {
        (assignment.staff_id, occupied_date)
        for assignment in assignments
        for occupied_date in _inclusive_dates(
            assignment.assigned_start_date,
            assignment.assigned_end_date,
        )
    }
    proposed.update(
        (buffer.staff_id, buffer_date)
        for buffer in buffers
        if buffer.active
        for buffer_date in buffer.dates
    )
    proposed.update(leave_occupancy)
    if external_keys.intersection(proposed):
        _raise_occupancy("leave transition conflicts with caregiver occupancy")


def _leave_occupancy_keys(
    intent: LeaveSubstitutionBatchIntent,
    selected: dict[date, OfficialScheduleFact],
) -> set[tuple[int, date]]:
    deferred_dates = _deferred_dates(intent)
    return {
        (
            selected[item.work_date].staff_id,
            item.work_date
            + timedelta(days=sum(value < item.work_date for value in deferred_dates)),
        )
        for item in intent.items
    }


def _build_generation(
    facts: AssignmentPlanFacts,
    assignments: tuple[AssignmentCandidate, ...],
    buffers: tuple[BufferCandidate, ...],
) -> SchedulingGenerationCandidate:
    cancelled_ids = tuple(
        item.assignment_id
        for item in sorted(facts.effective_assignments, key=lambda item: item.sequence)
    )
    return SchedulingGenerationCandidate(
        case_no=facts.case_no,
        generation_number=facts.scheduling_generation + 1,
        expected_aggregate_version=facts.scheduling_version,
        resulting_aggregate_version=facts.scheduling_version + 1,
        cancelled_assignment_ids=cancelled_ids,
        assignments=assignments,
        buffers=buffers,
    )


def _build_outcomes(
    intent: LeaveSubstitutionBatchIntent,
    selected: dict[date, OfficialScheduleFact],
    transformed: tuple[_ServiceOwner, ...],
    assignments: tuple[AssignmentCandidate, ...],
) -> tuple[LeaveOutcomeCandidate, ...]:
    transformed_by_schedule = {item.source_schedule_id: item for item in transformed}
    deferred_dates = _deferred_dates(intent)
    return tuple(
        _build_outcome(
            index,
            item,
            selected[item.work_date],
            transformed_by_schedule[item.original_schedule_id],
            assignments,
            deferred_dates,
        )
        for index, item in enumerate(intent.items)
    )


# Outcome lineage and resulting assignment ownership must be emitted together.
def _build_outcome(
    index,
    item,
    original,
    resulting,
    assignments,
    deferred_dates,
):
    assignment_key = next(
        assignment.candidate_key
        for assignment in assignments
        if resulting.service_date in assignment.service_dates
    )
    return LeaveOutcomeCandidate(
        item_index=index,
        original_schedule_id=original.schedule_id,
        original_assignment_id=original.assignment_id,
        original_staff_id=original.staff_id,
        original_work_date=original.work_date,
        resolution_type=item.resolution_type,
        leave_occupancy_date=(
            item.work_date
            + timedelta(
                days=sum(
                    value < item.work_date for value in deferred_dates
                )
            )
        ),
        resulting_service_date=resulting.service_date,
        resulting_staff_id=resulting.staff_id,
        resulting_assignment_key=assignment_key,
        is_double_pay=resulting.is_double_pay,
    )


def _deferred_dates(
    intent: LeaveSubstitutionBatchIntent,
) -> tuple[date, ...]:
    return tuple(
        item.work_date
        for item in intent.items
        if item.resolution_type is LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS
    )


def _impacted_staff_ids(
    facts: LeaveSubstitutionFacts,
    intent: LeaveSubstitutionBatchIntent,
) -> tuple[int, ...]:
    staff_ids = {
        item.staff_id for item in facts.assignment_plan.effective_assignments
    }
    staff_ids.update(
        item.substitute_staff_id
        for item in intent.items
        if item.substitute_staff_id is not None
    )
    return tuple(sorted(staff_ids))


def _candidate_payload(facts, intent, scheduling, outcomes):
    return {
        "case_no": facts.assignment_plan.case_no,
        "versions": {
            "order": facts.assignment_plan.order_version,
            "scheduling": facts.assignment_plan.scheduling_version,
            "client_finance": facts.assignment_plan.client_finance_version,
            "payroll": facts.assignment_plan.payroll_version,
        },
        "original_assignment_id": intent.original_assignment_id,
        "items": tuple(_item_payload(item) for item in intent.items),
        "generation": _generation_payload(scheduling),
        "outcomes": tuple(_outcome_payload(item) for item in outcomes),
    }


def _item_payload(item: LeaveSubstitutionItem) -> dict[str, object]:
    return {
        "original_schedule_id": item.original_schedule_id,
        "work_date": item.work_date.isoformat(),
        "resolution_type": item.resolution_type.value,
        "substitute_staff_id": item.substitute_staff_id,
        "is_double_pay": item.is_double_pay,
    }


# The complete generation projection participates in one deterministic fingerprint.
def _generation_payload(candidate: SchedulingGenerationCandidate):
    return {
        "number": candidate.generation_number,
        "cancelled_assignment_ids": candidate.cancelled_assignment_ids,
        "assignments": tuple(
            {
                "key": item.candidate_key,
                "staff_id": item.staff_id,
                "sequence": item.sequence,
                "start": item.assigned_start_date.isoformat(),
                "end": item.assigned_end_date.isoformat(),
                "service_dates": tuple(value.isoformat() for value in item.service_dates),
                "actual_hours": item.actual_hours,
                "lineage": item.lineage_source_assignment_ids,
                "double_pay_dates": tuple(
                    value.isoformat() for value in item.double_pay_dates
                ),
            }
            for item in candidate.assignments
        ),
    }


def _outcome_payload(item: LeaveOutcomeCandidate):
    return {
        "item_index": item.item_index,
        "original_schedule_id": item.original_schedule_id,
        "original_assignment_id": item.original_assignment_id,
        "original_work_date": item.original_work_date.isoformat(),
        "resolution_type": item.resolution_type.value,
        "leave_occupancy_date": item.leave_occupancy_date.isoformat(),
        "resulting_service_date": item.resulting_service_date.isoformat(),
        "resulting_staff_id": item.resulting_staff_id,
        "resulting_assignment_key": item.resulting_assignment_key,
        "is_double_pay": item.is_double_pay,
    }


def _inclusive_dates(start_date: date, end_date: date) -> tuple[date, ...]:
    return tuple(
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    )


def _require_date(value: object, field_name: str) -> None:
    if type(value) is not date:
        raise TypeError(f"{field_name} must be a calendar date")


def _raise_invalid(message: str) -> None:
    raise LeaveSubstitutionDomainError(
        LeaveSubstitutionIssue.INVALID_INTENT,
        message,
    )


def _raise_assignment(message: str) -> None:
    raise LeaveSubstitutionDomainError(
        LeaveSubstitutionIssue.ASSIGNMENT_NOT_FOUND,
        message,
    )


def _raise_ownership(message: str) -> None:
    raise LeaveSubstitutionDomainError(
        LeaveSubstitutionIssue.SERVICE_OWNERSHIP_CONFLICT,
        message,
    )


def _raise_coverage(message: str) -> None:
    raise LeaveSubstitutionDomainError(
        LeaveSubstitutionIssue.COVERAGE_INCOMPLETE,
        message,
    )


def _raise_occupancy(message: str) -> None:
    raise LeaveSubstitutionDomainError(
        LeaveSubstitutionIssue.STAFF_OCCUPANCY_CONFLICT,
        message,
    )

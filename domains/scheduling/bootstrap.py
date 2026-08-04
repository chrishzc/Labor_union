"""Pure eligibility rules for metadata-only legacy Scheduling bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum


class SchedulingBootstrapIssue(StrEnum):
    ASSIGNMENT_REQUIRED = "SCHED-BOOT-001"
    ASSIGNMENT_INTERVAL_INVALID = "SCHED-BOOT-002"
    ASSIGNMENT_SEQUENCE_INVALID = "SCHED-BOOT-003"
    SCHEDULE_OWNER_MISSING = "SCHED-BOOT-004"
    SCHEDULE_OWNER_MISMATCH = "SCHED-BOOT-005"
    ASSIGNMENT_DATE_COVERAGE_MISMATCH = "SCHED-BOOT-006"
    CASE_SERVICE_DAYS_MISMATCH = "SCHED-BOOT-007"
    ACTUAL_HOURS_MISMATCH = "SCHED-BOOT-008"
    STAFF_OCCUPANCY_CONFLICT = "SCHED-BOOT-009"
    EXISTING_GENERATION_CONFLICT = "SCHED-BOOT-010"


@dataclass(frozen=True, slots=True)
class LegacyOrderSchedulingFacts:
    case_no: str
    service_days: int
    service_hours_per_day: int
    service_started: bool


@dataclass(frozen=True, slots=True)
class LegacyAssignmentBootstrapFact:
    assignment_id: int
    case_no: str
    staff_id: int
    sequence: int
    assigned_start_date: date | None
    assigned_end_date: date | None
    actual_hours: Decimal | None
    generation_id: int | None = None


@dataclass(frozen=True, slots=True)
class LegacyScheduleBootstrapFact:
    schedule_id: int
    case_no: str
    staff_id: int
    assignment_id: int | None
    work_date: date
    is_work_day: bool
    generation_id: int | None = None


@dataclass(frozen=True, slots=True)
class ExternalStaffOccupancyFact:
    staff_id: int
    occupancy_date: date
    case_no: str


@dataclass(frozen=True, slots=True)
class SchedulingBootstrapFacts:
    order: LegacyOrderSchedulingFacts
    assignments: tuple[LegacyAssignmentBootstrapFact, ...]
    schedules: tuple[LegacyScheduleBootstrapFact, ...]
    external_occupancy: tuple[ExternalStaffOccupancyFact, ...] = ()


@dataclass(frozen=True, slots=True)
class BootstrapAssignmentMetadata:
    assignment_id: int
    candidate_key: str
    staff_id: int
    schedule_ids: tuple[int, ...]
    interval_dates: tuple[date, ...]
    buffer_dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class SchedulingBootstrapCandidate:
    case_no: str
    generation_number: int
    assignments: tuple[BootstrapAssignmentMetadata, ...]


@dataclass(frozen=True, slots=True)
class SchedulingBootstrapDecision:
    candidate: SchedulingBootstrapCandidate | None
    issues: tuple[SchedulingBootstrapIssue, ...]


def evaluate_scheduling_bootstrap(
    facts: SchedulingBootstrapFacts,
) -> SchedulingBootstrapDecision:
    issues = _collect_structural_issues(facts)
    metadata = _build_metadata(facts) if not issues else ()
    if metadata:
        issues.update(_occupancy_issues(facts, metadata))
    if issues:
        return SchedulingBootstrapDecision(None, tuple(sorted(issues)))
    return SchedulingBootstrapDecision(
        SchedulingBootstrapCandidate(facts.order.case_no, 1, metadata),
        (),
    )


def _collect_structural_issues(
    facts: SchedulingBootstrapFacts,
) -> set[SchedulingBootstrapIssue]:
    issues: set[SchedulingBootstrapIssue] = set()
    if not facts.assignments:
        issues.add(SchedulingBootstrapIssue.ASSIGNMENT_REQUIRED)
        return issues
    _check_generation_state(facts, issues)
    _check_assignment_shape(facts, issues)
    _check_schedule_ownership(facts, issues)
    _check_service_conservation(facts, issues)
    return issues


def _check_generation_state(facts, issues) -> None:
    if any(item.generation_id is not None for item in facts.assignments):
        issues.add(SchedulingBootstrapIssue.EXISTING_GENERATION_CONFLICT)
    if any(item.generation_id is not None for item in facts.schedules):
        issues.add(SchedulingBootstrapIssue.EXISTING_GENERATION_CONFLICT)


def _check_assignment_shape(facts, issues) -> None:
    ordered = sorted(facts.assignments, key=lambda item: item.sequence)
    if tuple(item.sequence for item in ordered) != tuple(range(1, len(ordered) + 1)):
        issues.add(SchedulingBootstrapIssue.ASSIGNMENT_SEQUENCE_INVALID)
    if any(not _valid_interval(item) for item in ordered):
        issues.add(SchedulingBootstrapIssue.ASSIGNMENT_INTERVAL_INVALID)


def _valid_interval(assignment: LegacyAssignmentBootstrapFact) -> bool:
    return (
        assignment.case_no != ""
        and assignment.assigned_start_date is not None
        and assignment.assigned_end_date is not None
        and assignment.assigned_end_date >= assignment.assigned_start_date
    )


def _check_schedule_ownership(facts, issues) -> None:
    assignments = {item.assignment_id: item for item in facts.assignments}
    if any(item.assignment_id is None for item in facts.schedules):
        issues.add(SchedulingBootstrapIssue.SCHEDULE_OWNER_MISSING)
    for schedule in facts.schedules:
        owner = assignments.get(schedule.assignment_id)
        if owner is not None and _schedule_matches(schedule, owner):
            continue
        if schedule.assignment_id is not None:
            issues.add(SchedulingBootstrapIssue.SCHEDULE_OWNER_MISMATCH)


def _schedule_matches(schedule, assignment) -> bool:
    return (
        schedule.case_no == assignment.case_no
        and schedule.staff_id == assignment.staff_id
        and assignment.assigned_start_date <= schedule.work_date
        and schedule.work_date <= assignment.assigned_end_date
    )


def _check_service_conservation(facts, issues) -> None:
    workday_count = sum(item.is_work_day for item in facts.schedules)
    if workday_count != facts.order.service_days:
        issues.add(SchedulingBootstrapIssue.CASE_SERVICE_DAYS_MISMATCH)
    schedules_by_assignment = _schedules_by_assignment(facts.schedules)
    for assignment in facts.assignments:
        schedules = schedules_by_assignment.get(assignment.assignment_id, ())
        _check_assignment_dates(assignment, schedules, issues)
        _check_actual_hours(facts, assignment, schedules, issues)


def _schedules_by_assignment(schedules):
    result: dict[int, list[LegacyScheduleBootstrapFact]] = {}
    for schedule in schedules:
        if schedule.assignment_id is not None:
            result.setdefault(schedule.assignment_id, []).append(schedule)
    return result


def _check_assignment_dates(assignment, schedules, issues) -> None:
    if not _valid_interval(assignment):
        return
    actual_dates = tuple(sorted(item.work_date for item in schedules))
    expected_dates = _inclusive_dates(
        assignment.assigned_start_date,
        assignment.assigned_end_date,
    )
    if actual_dates != expected_dates:
        issues.add(SchedulingBootstrapIssue.ASSIGNMENT_DATE_COVERAGE_MISMATCH)


def _check_actual_hours(facts, assignment, schedules, issues) -> None:
    workday_count = sum(item.is_work_day for item in schedules)
    expected = Decimal(workday_count * facts.order.service_hours_per_day)
    if assignment.actual_hours != expected:
        issues.add(SchedulingBootstrapIssue.ACTUAL_HOURS_MISMATCH)


def _build_metadata(
    facts: SchedulingBootstrapFacts,
) -> tuple[BootstrapAssignmentMetadata, ...]:
    schedules = _schedules_by_assignment(facts.schedules)
    return tuple(
        _assignment_metadata(facts, assignment, schedules[assignment.assignment_id])
        for assignment in sorted(facts.assignments, key=lambda item: item.sequence)
    )


def _assignment_metadata(facts, assignment, schedules):
    interval = _inclusive_dates(
        assignment.assigned_start_date,
        assignment.assigned_end_date,
    )
    buffers = () if facts.order.service_started else _buffer_dates(interval[-1])
    return BootstrapAssignmentMetadata(
        assignment.assignment_id,
        f"{facts.order.case_no}:g1:a{assignment.sequence}",
        assignment.staff_id,
        tuple(sorted(item.schedule_id for item in schedules)),
        interval,
        buffers,
    )


def _occupancy_issues(facts, metadata) -> set[SchedulingBootstrapIssue]:
    occupied = {
        (item.staff_id, item.occupancy_date)
        for item in facts.external_occupancy
        if item.case_no != facts.order.case_no
    }
    issues: set[SchedulingBootstrapIssue] = set()
    for assignment in metadata:
        for occupancy_date in assignment.interval_dates + assignment.buffer_dates:
            identity = (assignment.staff_id, occupancy_date)
            if identity in occupied:
                issues.add(SchedulingBootstrapIssue.STAFF_OCCUPANCY_CONFLICT)
            occupied.add(identity)
    return issues


def _buffer_dates(end_date: date) -> tuple[date, ...]:
    return tuple(end_date + timedelta(days=offset) for offset in range(1, 8))


def _inclusive_dates(start_date: date, end_date: date) -> tuple[date, ...]:
    return tuple(
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    )

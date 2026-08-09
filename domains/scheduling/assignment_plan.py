"""Pure Assignment Plan contracts and generation candidate builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from domains.scheduling.generation import (
    AssignmentCandidate,
    BufferCandidate,
    SchedulingGenerationCandidate,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_BUFFER_DAY_COUNT = 7
_CASE_NUMBER_MAXIMUM_LENGTH = 50
_MAXIMUM_SEGMENT_COUNT = 4


class AssignmentPlanIssue(StrEnum):
    INVALID_INTENT = "invalid_scheduling_intent"
    COVERAGE_INCOMPLETE = "coverage_incomplete"
    SERVICE_OWNERSHIP_CONFLICT = "service_ownership_conflict"
    STAFF_OCCUPANCY_CONFLICT = "staff_occupancy_conflict"


class AssignmentPlanDomainError(ValueError):
    def __init__(self, issue: AssignmentPlanIssue, message: str) -> None:
        super().__init__(message)
        self.issue = issue


@dataclass(frozen=True, slots=True)
class EffectiveAssignmentFact:
    assignment_id: int
    staff_id: int
    sequence: int
    assigned_start_date: date | None = None
    assigned_end_date: date | None = None
    official_service_dates: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        require_positive_integer(self.staff_id, "staff id")
        require_positive_integer(self.sequence, "assignment sequence")
        _validate_effective_assignment_detail(self)


@dataclass(frozen=True, slots=True)
class StaffOccupancyFact:
    staff_id: int
    occupancy_date: date
    source_case_no: str

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "staff id")
        _require_calendar_date(self.occupancy_date, "occupancy date")
        require_canonical_text(
            self.source_case_no,
            "source case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class AssignmentPlanSegmentIntent:
    staff_id: int
    assigned_start_date: date
    assigned_end_date: date
    official_service_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "staff id")
        _require_calendar_date(self.assigned_start_date, "assigned start date")
        _require_calendar_date(self.assigned_end_date, "assigned end date")
        _validate_segment_interval(self)
        _validate_official_service_dates(self)


@dataclass(frozen=True, slots=True)
class AssignmentPlanIntent:
    segments: tuple[AssignmentPlanSegmentIntent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.segments, tuple):
            raise TypeError("assignment plan segments must be a tuple")
        if not 1 <= len(self.segments) <= _MAXIMUM_SEGMENT_COUNT:
            _raise_invalid("assignment plan requires one to four segments")
        if any(
            not isinstance(segment, AssignmentPlanSegmentIntent)
            for segment in self.segments
        ):
            raise TypeError("assignment plan contains an invalid segment")
        _validate_consecutive_intervals(self.segments)


@dataclass(frozen=True, slots=True)
class AssignmentPlanFacts:
    case_no: str
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int
    payroll_version: int
    contracted_service_days: int
    service_hours_per_day: int
    service_started: bool
    effective_assignments: tuple[EffectiveAssignmentFact, ...] = ()
    external_occupancy: tuple[StaffOccupancyFact, ...] = ()
    current_waiting_lock_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no,
            "case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        _validate_fact_versions(self)
        require_positive_integer(
            self.contracted_service_days,
            "contracted service days",
        )
        require_positive_integer(
            self.service_hours_per_day,
            "service hours per day",
        )
        _validate_fact_collections(self)


@dataclass(frozen=True, slots=True)
class AssignmentPlanCandidate:
    scheduling: SchedulingGenerationCandidate
    impacted_staff_ids: tuple[int, ...]
    waiting_lock_ids: tuple[int, ...]
    fingerprint: PreviewFingerprint


def build_assignment_plan_candidate(
    facts: AssignmentPlanFacts,
    intent: AssignmentPlanIntent,
) -> AssignmentPlanCandidate:
    _validate_service_conservation(facts, intent)
    assignments = _build_assignments(facts, intent)
    buffers = _build_buffers(assignments, active=not facts.service_started)
    _validate_internal_occupancy(assignments, buffers)
    _validate_external_occupancy(facts, assignments, buffers)
    scheduling = _build_generation(facts, assignments, buffers)
    fingerprint = fingerprint_payload(_candidate_payload(facts, intent, scheduling))
    return AssignmentPlanCandidate(
        scheduling=scheduling,
        impacted_staff_ids=impacted_staff_ids(facts, intent),
        waiting_lock_ids=facts.current_waiting_lock_ids,
        fingerprint=fingerprint,
    )


def impacted_staff_ids(
    facts: AssignmentPlanFacts,
    intent: AssignmentPlanIntent,
) -> tuple[int, ...]:
    staff_ids = {segment.staff_id for segment in intent.segments}
    staff_ids.update(item.staff_id for item in facts.effective_assignments)
    return tuple(sorted(staff_ids))


def _validate_segment_interval(segment: AssignmentPlanSegmentIntent) -> None:
    if segment.assigned_end_date < segment.assigned_start_date:
        _raise_invalid("assignment segment interval is inverted")


def _validate_effective_assignment_detail(
    assignment: EffectiveAssignmentFact,
) -> None:
    dates = (
        assignment.assigned_start_date,
        assignment.assigned_end_date,
    )
    if dates == (None, None) and not assignment.official_service_dates:
        return
    if any(type(value) is not date for value in dates):
        raise TypeError("effective assignment interval is incomplete")
    if assignment.assigned_end_date < assignment.assigned_start_date:
        raise ValueError("effective assignment interval is inverted")
    if not assignment.official_service_dates:
        raise ValueError("effective assignment service dates are required")
    service_dates = assignment.official_service_dates
    if service_dates != tuple(sorted(set(service_dates))):
        raise ValueError("effective assignment service dates are not canonical")
    if any(
        value < assignment.assigned_start_date
        or value > assignment.assigned_end_date
        for value in service_dates
    ):
        raise ValueError("effective assignment service date is outside interval")


def _validate_official_service_dates(
    segment: AssignmentPlanSegmentIntent,
) -> None:
    service_dates = segment.official_service_dates
    if not isinstance(service_dates, tuple) or not service_dates:
        _raise_invalid("each assignment segment requires official service dates")
    if any(type(value) is not date for value in service_dates):
        _raise_invalid("half-day or non-calendar service dates are not supported")
    if service_dates != tuple(sorted(set(service_dates))):
        _raise_ownership("official service dates must be sorted and unique")
    if any(not _date_is_within_segment(value, segment) for value in service_dates):
        _raise_coverage("official service date falls outside its segment")


def _validate_consecutive_intervals(
    segments: tuple[AssignmentPlanSegmentIntent, ...],
) -> None:
    for previous, current in zip(segments, segments[1:]):
        expected_start = previous.assigned_end_date + timedelta(days=1)
        if current.assigned_start_date == expected_start:
            continue
        if current.assigned_start_date <= previous.assigned_end_date:
            _raise_invalid("assignment segment intervals overlap")
        _raise_invalid("assignment segment intervals contain a gap")


def _validate_service_conservation(
    facts: AssignmentPlanFacts,
    intent: AssignmentPlanIntent,
) -> None:
    service_dates = tuple(
        service_date
        for segment in intent.segments
        for service_date in segment.official_service_dates
    )
    if len(service_dates) != len(set(service_dates)):
        _raise_ownership("one official service date has multiple owners")
    if len(service_dates) != facts.contracted_service_days:
        _raise_coverage("official service days do not conserve the contract")


def _build_assignments(
    facts: AssignmentPlanFacts,
    intent: AssignmentPlanIntent,
) -> tuple[AssignmentCandidate, ...]:
    return tuple(
        _build_assignment(
            facts,
            segment,
            sequence,
            _lineage_for_segment(facts, segment),
        )
        for sequence, segment in enumerate(intent.segments, start=1)
    )


def _lineage_for_segment(
    facts: AssignmentPlanFacts,
    segment: AssignmentPlanSegmentIntent,
) -> tuple[int, ...]:
    sources = tuple(
        assignment.assignment_id
        for assignment in facts.effective_assignments
        if _assignment_overlaps_segment(assignment, segment)
    )
    return tuple(sorted(set(sources)))


def _assignment_overlaps_segment(
    assignment: EffectiveAssignmentFact,
    segment: AssignmentPlanSegmentIntent,
) -> bool:
    if set(assignment.official_service_dates).intersection(
        segment.official_service_dates
    ):
        return True
    if assignment.assigned_start_date is None:
        return False
    return (
        assignment.assigned_start_date <= segment.assigned_end_date
        and assignment.assigned_end_date >= segment.assigned_start_date
    )


# Kept cohesive because one immutable assignment comes from one validated segment.
def _build_assignment(
    facts: AssignmentPlanFacts,
    segment: AssignmentPlanSegmentIntent,
    sequence: int,
    lineage: tuple[int, ...],
) -> AssignmentCandidate:
    candidate_key = (
        f"{facts.case_no}:g{facts.scheduling_generation + 1}:a{sequence}"
    )
    return AssignmentCandidate(
        candidate_key=candidate_key,
        source_assignment_id=None,
        staff_id=segment.staff_id,
        sequence=sequence,
        assigned_start_date=segment.assigned_start_date,
        assigned_end_date=segment.assigned_end_date,
        service_dates=segment.official_service_dates,
        actual_hours=(
            len(segment.official_service_dates) * facts.service_hours_per_day
        ),
        lineage_source_assignment_ids=lineage,
    )


def _build_buffers(
    assignments: tuple[AssignmentCandidate, ...],
    *,
    active: bool,
) -> tuple[BufferCandidate, ...]:
    return tuple(_build_buffer(assignment, active) for assignment in assignments)


def _build_buffer(
    assignment: AssignmentCandidate,
    active: bool,
) -> BufferCandidate:
    dates = tuple(
        assignment.assigned_end_date + timedelta(days=offset)
        for offset in range(1, _BUFFER_DAY_COUNT + 1)
    )
    return BufferCandidate(
        candidate_key=f"{assignment.candidate_key}:buffer",
        staff_id=assignment.staff_id,
        dates=dates,
        active=active,
    )


def _validate_internal_occupancy(
    assignments: tuple[AssignmentCandidate, ...],
    buffers: tuple[BufferCandidate, ...],
) -> None:
    occupied: set[tuple[int, date]] = set()
    for assignment in assignments:
        _claim_dates(occupied, assignment.staff_id, _assignment_interval(assignment))
    for buffer in buffers:
        if buffer.active:
            _claim_dates(occupied, buffer.staff_id, buffer.dates)


def _validate_external_occupancy(
    facts: AssignmentPlanFacts,
    assignments: tuple[AssignmentCandidate, ...],
    buffers: tuple[BufferCandidate, ...],
) -> None:
    external = {
        (item.staff_id, item.occupancy_date)
        for item in facts.external_occupancy
        if item.source_case_no != facts.case_no
    }
    proposed = _proposed_occupancy(assignments, buffers)
    if external.intersection(proposed):
        _raise_occupancy("assignment interval or active buffer is occupied")


def _proposed_occupancy(
    assignments: tuple[AssignmentCandidate, ...],
    buffers: tuple[BufferCandidate, ...],
) -> set[tuple[int, date]]:
    occupied = {
        (item.staff_id, value)
        for item in assignments
        for value in _assignment_interval(item)
    }
    occupied.update(
        (item.staff_id, value)
        for item in buffers
        if item.active
        for value in item.dates
    )
    return occupied


def _claim_dates(
    occupied: set[tuple[int, date]],
    staff_id: int,
    dates: tuple[date, ...],
) -> None:
    for occupied_date in dates:
        identity = (staff_id, occupied_date)
        if identity in occupied:
            _raise_occupancy("one caregiver has overlapping occupancy")
        occupied.add(identity)


def _build_generation(
    facts: AssignmentPlanFacts,
    assignments: tuple[AssignmentCandidate, ...],
    buffers: tuple[BufferCandidate, ...],
) -> SchedulingGenerationCandidate:
    return SchedulingGenerationCandidate(
        case_no=facts.case_no,
        generation_number=facts.scheduling_generation + 1,
        expected_aggregate_version=facts.scheduling_version,
        resulting_aggregate_version=facts.scheduling_version + 1,
        cancelled_assignment_ids=_cancelled_assignment_ids(facts),
        assignments=assignments,
        buffers=buffers,
    )


def _cancelled_assignment_ids(
    facts: AssignmentPlanFacts,
) -> tuple[int, ...]:
    ordered = sorted(
        facts.effective_assignments,
        key=lambda item: item.sequence,
    )
    return tuple(item.assignment_id for item in ordered)


def _candidate_payload(
    facts: AssignmentPlanFacts,
    intent: AssignmentPlanIntent,
    scheduling: SchedulingGenerationCandidate,
) -> dict[str, object]:
    return {
        "case_no": facts.case_no,
        "versions": _version_payload(facts),
        "service_started": facts.service_started,
        "contracted_service_days": facts.contracted_service_days,
        "service_hours_per_day": facts.service_hours_per_day,
        "current_waiting_lock_ids": facts.current_waiting_lock_ids,
        "segments": tuple(_segment_payload(item) for item in intent.segments),
        "generation": _generation_payload(scheduling),
    }


def _version_payload(facts: AssignmentPlanFacts) -> dict[str, int]:
    return {
        "order": facts.order_version,
        "scheduling": facts.scheduling_version,
        "client_finance": facts.client_finance_version,
        "payroll": facts.payroll_version,
    }


def _segment_payload(segment: AssignmentPlanSegmentIntent) -> dict[str, object]:
    return {
        "staff_id": segment.staff_id,
        "assigned_start_date": segment.assigned_start_date.isoformat(),
        "assigned_end_date": segment.assigned_end_date.isoformat(),
        "official_service_dates": tuple(
            value.isoformat() for value in segment.official_service_dates
        ),
    }


def _generation_payload(
    candidate: SchedulingGenerationCandidate,
) -> dict[str, object]:
    return {
        "generation_number": candidate.generation_number,
        "cancelled_assignment_ids": candidate.cancelled_assignment_ids,
        "assignments": tuple(
            _assignment_payload(item) for item in candidate.assignments
        ),
        "buffers": tuple(
            _buffer_payload(item) for item in candidate.buffers
        ),
    }


def _assignment_payload(assignment: AssignmentCandidate) -> dict[str, object]:
    return {
        "key": assignment.candidate_key,
        "staff_id": assignment.staff_id,
        "sequence": assignment.sequence,
        "actual_hours": assignment.actual_hours,
        "lineage": assignment.lineage_source_assignment_ids,
    }


def _buffer_payload(buffer: BufferCandidate) -> dict[str, object]:
    return {
        "key": buffer.candidate_key,
        "staff_id": buffer.staff_id,
        "dates": tuple(value.isoformat() for value in buffer.dates),
        "active": buffer.active,
    }


def _validate_fact_versions(facts: AssignmentPlanFacts) -> None:
    require_nonnegative_integer(facts.order_version, "order version")
    require_nonnegative_integer(facts.scheduling_version, "scheduling version")
    require_nonnegative_integer(
        facts.scheduling_generation,
        "scheduling generation",
    )
    require_nonnegative_integer(
        facts.client_finance_version,
        "client finance version",
    )
    require_nonnegative_integer(facts.payroll_version, "payroll version")


def _validate_fact_collections(facts: AssignmentPlanFacts) -> None:
    if not isinstance(facts.service_started, bool):
        raise TypeError("service started must be bool")
    if not isinstance(facts.effective_assignments, tuple):
        raise TypeError("effective assignments must be a tuple")
    if not isinstance(facts.external_occupancy, tuple):
        raise TypeError("external occupancy must be a tuple")
    lock_ids = facts.current_waiting_lock_ids
    if not isinstance(lock_ids, tuple):
        raise TypeError("waiting lock ids must be a tuple")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in lock_ids
    ):
        raise ValueError("waiting lock ids must be positive integers")
    if lock_ids != tuple(sorted(set(lock_ids))):
        raise ValueError("waiting lock ids must be canonical")


def _assignment_interval(
    assignment: AssignmentCandidate,
) -> tuple[date, ...]:
    day_count = (assignment.assigned_end_date - assignment.assigned_start_date).days
    return tuple(
        assignment.assigned_start_date + timedelta(days=offset)
        for offset in range(day_count + 1)
    )


def _date_is_within_segment(
    service_date: date,
    segment: AssignmentPlanSegmentIntent,
) -> bool:
    return segment.assigned_start_date <= service_date <= segment.assigned_end_date


def _require_calendar_date(value: object, field_name: str) -> None:
    if type(value) is not date:
        _raise_invalid(f"{field_name} must be a full calendar date")


def _raise_invalid(message: str) -> None:
    raise AssignmentPlanDomainError(AssignmentPlanIssue.INVALID_INTENT, message)


def _raise_coverage(message: str) -> None:
    raise AssignmentPlanDomainError(
        AssignmentPlanIssue.COVERAGE_INCOMPLETE,
        message,
    )


def _raise_ownership(message: str) -> None:
    raise AssignmentPlanDomainError(
        AssignmentPlanIssue.SERVICE_OWNERSHIP_CONFLICT,
        message,
    )


def _raise_occupancy(message: str) -> None:
    raise AssignmentPlanDomainError(
        AssignmentPlanIssue.STAFF_OCCUPANCY_CONFLICT,
        message,
    )

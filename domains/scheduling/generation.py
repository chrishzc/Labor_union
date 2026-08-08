"""Pure scheduling generation replacement candidate builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping
from datetime import date, timedelta

from domains.orders.terms import OrderTerms
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_BUFFER_DAYS = 7
_CASE_NUMBER_MAXIMUM_LENGTH = 50


@dataclass(frozen=True, slots=True)
class EffectiveAssignmentSegment:
    assignment_id: int
    staff_id: int
    sequence: int
    service_day_count: int
    assigned_start_date: date
    assigned_end_date: date
    official_service_dates: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        require_positive_integer(self.staff_id, "staff id")
        require_positive_integer(self.sequence, "assignment sequence")
        require_positive_integer(self.service_day_count, "segment service days")
        if not isinstance(self.assigned_start_date, date):
            raise TypeError("assigned start date must be date")
        if not isinstance(self.assigned_end_date, date):
            raise TypeError("assigned end date must be date")
        if self.assigned_end_date < self.assigned_start_date:
            raise ValueError("assigned interval is inverted")
        self._validate_official_service_dates()

    def _validate_official_service_dates(self) -> None:
        service_dates = self.official_service_dates
        if not isinstance(service_dates, tuple):
            raise TypeError("official service dates must be a tuple")
        if not service_dates:
            return
        if len(service_dates) != self.service_day_count:
            raise ValueError("official service day count does not match segment")
        if service_dates != tuple(sorted(set(service_dates))):
            raise ValueError("official service dates must be sorted and unique")
        if any(
            value < self.assigned_start_date or value > self.assigned_end_date
            for value in service_dates
        ):
            raise ValueError("official service date is outside assignment interval")


@dataclass(frozen=True, slots=True)
class SchedulingGenerationFacts:
    case_no: str
    aggregate_version: int
    generation_number: int
    segments: tuple[EffectiveAssignmentSegment, ...]
    service_started: bool = False

    # Kept cohesive so one immutable aggregate snapshot validates as a unit.
    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no,
            "case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        require_nonnegative_integer(
            self.aggregate_version,
            "scheduling aggregate version",
        )
        require_nonnegative_integer(
            self.generation_number,
            "scheduling generation number",
        )
        if not isinstance(self.segments, tuple):
            raise TypeError("scheduling segments must be a tuple")
        if any(
            not isinstance(segment, EffectiveAssignmentSegment)
            for segment in self.segments
        ):
            raise TypeError("scheduling segments contain an invalid value")
        if not isinstance(self.service_started, bool):
            raise TypeError("service started must be bool")


@dataclass(frozen=True, slots=True)
class AssignmentCandidate:
    candidate_key: str
    source_assignment_id: int | None
    staff_id: int
    sequence: int
    assigned_start_date: date
    assigned_end_date: date
    service_dates: tuple[date, ...]
    actual_hours: int
    lineage_source_assignment_ids: tuple[int, ...] = ()
    double_pay_dates: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        source_ids = self.lineage_source_assignment_ids
        if not source_ids and self.source_assignment_id is not None:
            source_ids = (self.source_assignment_id,)
            object.__setattr__(self, "lineage_source_assignment_ids", source_ids)
        _validate_lineage_sources(self.source_assignment_id, source_ids)
        _validate_double_pay_dates(self.service_dates, self.double_pay_dates)


@dataclass(frozen=True, slots=True)
class BufferCandidate:
    candidate_key: str
    staff_id: int
    dates: tuple[date, ...]
    active: bool


@dataclass(frozen=True, slots=True)
class SchedulingGenerationCandidate:
    case_no: str
    generation_number: int
    expected_aggregate_version: int
    resulting_aggregate_version: int
    cancelled_assignment_ids: tuple[int, ...]
    assignments: tuple[AssignmentCandidate, ...]
    buffers: tuple[BufferCandidate, ...]


@dataclass(frozen=True, slots=True)
class AssignmentIdentityResolution:
    assignment_id_by_candidate_key: Mapping[str, int]

    def __post_init__(self) -> None:
        copied = dict(self.assignment_id_by_candidate_key)
        if not copied:
            raise ValueError("assignment identity resolution cannot be empty")
        if any(not key.strip() for key in copied):
            raise ValueError("assignment candidate key cannot be empty")
        if any(not isinstance(value, int) or value <= 0 for value in copied.values()):
            raise ValueError("resolved assignment ids must be positive integers")
        object.__setattr__(
            self,
            "assignment_id_by_candidate_key",
            MappingProxyType(copied),
        )

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> AssignmentIdentityResolution:
        return self


@dataclass(frozen=True, slots=True)
class EmptyAssignmentIdentityResolution:
    assignment_id_by_candidate_key: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if self.assignment_id_by_candidate_key:
            raise ValueError("empty assignment resolution cannot contain identities")

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> EmptyAssignmentIdentityResolution:
        return self


# Kept cohesive so generation versions and every derived collection stay aligned.
def build_generation_candidate(
    facts: SchedulingGenerationFacts,
    terms: OrderTerms,
    planned_service_dates: tuple[date, ...],
) -> SchedulingGenerationCandidate:
    _validate_generation_inputs(facts, terms, planned_service_dates)
    assignments = _build_assignments(facts, terms, planned_service_dates)
    buffers = tuple(
        _build_buffer(assignment, active=not facts.service_started)
        for assignment in assignments
    )
    _validate_candidate_occupancy(assignments, buffers)
    return SchedulingGenerationCandidate(
        case_no=facts.case_no,
        generation_number=facts.generation_number + 1,
        expected_aggregate_version=facts.aggregate_version,
        resulting_aggregate_version=facts.aggregate_version + 1,
        cancelled_assignment_ids=tuple(
            segment.assignment_id for segment in _ordered_segments(facts)
        ),
        assignments=assignments,
        buffers=buffers,
    )


def _validate_generation_inputs(
    facts: SchedulingGenerationFacts,
    terms: OrderTerms,
    planned_service_dates: tuple[date, ...],
) -> None:
    if not facts.segments:
        raise ValueError("scheduling_segments_required")
    if sum(segment.service_day_count for segment in facts.segments) != terms.service_days:
        raise ValueError("scheduling_reallocation_required")
    if len(planned_service_dates) != terms.service_days:
        raise ValueError("service_days_mismatch")
    if planned_service_dates != tuple(sorted(set(planned_service_dates))):
        raise ValueError("service dates must be sorted and unique")


def _validate_lineage_sources(
    primary_source_id: int | None,
    source_ids: tuple[int, ...],
) -> None:
    if not isinstance(source_ids, tuple):
        raise TypeError("assignment lineage sources must be a tuple")
    if any(not isinstance(value, int) or value <= 0 for value in source_ids):
        raise ValueError("assignment lineage sources must be positive integers")
    if source_ids != tuple(sorted(set(source_ids))):
        raise ValueError("assignment lineage sources must be canonical")
    if primary_source_id is None:
        return
    require_positive_integer(primary_source_id, "source assignment id")
    if primary_source_id not in source_ids:
        raise ValueError("primary source assignment is absent from lineage")


def _validate_double_pay_dates(
    service_dates: tuple[date, ...],
    double_pay_dates: tuple[date, ...],
) -> None:
    if not isinstance(double_pay_dates, tuple):
        raise TypeError("double-pay dates must be a tuple")
    if double_pay_dates != tuple(sorted(set(double_pay_dates))):
        raise ValueError("double-pay dates must be canonical")
    if not set(double_pay_dates).issubset(service_dates):
        raise ValueError("double-pay dates must be official service dates")


def _ordered_segments(
    facts: SchedulingGenerationFacts,
) -> tuple[EffectiveAssignmentSegment, ...]:
    ordered = tuple(sorted(facts.segments, key=lambda segment: segment.sequence))
    sequences = tuple(segment.sequence for segment in ordered)
    if sequences != tuple(range(1, len(ordered) + 1)):
        raise ValueError("assignment sequences must be contiguous")
    return ordered


def _build_assignments(
    facts: SchedulingGenerationFacts,
    terms: OrderTerms,
    planned_service_dates: tuple[date, ...],
) -> tuple[AssignmentCandidate, ...]:
    assignments: list[AssignmentCandidate] = []
    offset = 0
    for segment in _ordered_segments(facts):
        segment_dates = planned_service_dates[
            offset : offset + segment.service_day_count
        ]
        assignments.append(_build_assignment(facts, terms, segment, segment_dates))
        offset += segment.service_day_count
    return tuple(assignments)


def _build_assignment(
    facts: SchedulingGenerationFacts,
    terms: OrderTerms,
    segment: EffectiveAssignmentSegment,
    service_dates: tuple[date, ...],
) -> AssignmentCandidate:
    candidate_key = (
        f"{facts.case_no}:g{facts.generation_number + 1}:a{segment.sequence}"
    )
    return AssignmentCandidate(
        candidate_key=candidate_key,
        source_assignment_id=segment.assignment_id,
        staff_id=segment.staff_id,
        sequence=segment.sequence,
        assigned_start_date=segment.assigned_start_date,
        assigned_end_date=segment.assigned_end_date,
        service_dates=service_dates,
        actual_hours=len(service_dates) * terms.service_hours_per_day,
    )


def _build_buffer(
    assignment: AssignmentCandidate,
    *,
    active: bool,
) -> BufferCandidate:
    dates = tuple(
        assignment.assigned_end_date + timedelta(days=offset)
        for offset in range(1, _BUFFER_DAYS + 1)
    )
    return BufferCandidate(
        candidate_key=f"{assignment.candidate_key}:buffer",
        staff_id=assignment.staff_id,
        dates=dates,
        active=active,
    )


def _validate_candidate_occupancy(
    assignments: tuple[AssignmentCandidate, ...],
    buffers: tuple[BufferCandidate, ...],
) -> None:
    occupied: set[tuple[int, date]] = set()
    for assignment in assignments:
        for occupied_date in _inclusive_dates(
            assignment.assigned_start_date,
            assignment.assigned_end_date,
        ):
            _claim_occupancy(occupied, assignment.staff_id, occupied_date)
    for buffer in buffers:
        if not buffer.active:
            continue
        for buffer_date in buffer.dates:
            _claim_occupancy(occupied, buffer.staff_id, buffer_date)


def _claim_occupancy(
    occupied: set[tuple[int, date]],
    staff_id: int,
    occupied_date: date,
) -> None:
    identity = (staff_id, occupied_date)
    if identity in occupied:
        raise ValueError("buffer_conflict")
    occupied.add(identity)


def _inclusive_dates(start_date: date, end_date: date) -> tuple[date, ...]:
    return tuple(
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    )

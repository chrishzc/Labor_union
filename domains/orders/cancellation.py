"""Pure cancellation candidate from confirmed daily service roots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from domains.scheduling.generation import (
    AssignmentCandidate,
    SchedulingGenerationCandidate,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_REASON_MAXIMUM_LENGTH = 500


class CancellationBlocker(StrEnum):
    AFTER_FULL_SERVICE = "order_cancellation_after_full_service"
    ACTUAL_SERVICE_FACTS_REQUIRED = "cancellation_actual_service_facts_required"
    SERVICE_DATA_LOCKED_INCONSISTENT = (
        "cancellation_service_data_locked_inconsistent"
    )
    SERVICE_DATE_BEFORE_ACTUAL_START = "cancellation_service_date_before_actual_start"
    SERVICE_DATE_IN_FUTURE = "cancellation_service_date_in_future"
    SERVICE_DAY_REASON_REQUIRED = "cancellation_service_day_reason_required"
    SERVICE_START_FACT_INCONSISTENT = (
        "cancellation_service_start_fact_inconsistent"
    )
    SERVICE_OWNERSHIP_CONFLICT = "cancellation_service_ownership_conflict"
    SERVICE_DAYS_EXCEED_CONTRACT = "cancellation_service_days_exceed_contract"
    PAYROLL_RATE_POLICY_NOT_FOUND = (
        "cancellation_payroll_rate_policy_not_found"
    )


class CancellationCandidateError(ValueError):
    def __init__(self, blocker: CancellationBlocker) -> None:
        self.blocker = blocker
        super().__init__(blocker.value)


@dataclass(frozen=True, slots=True)
class CancellationOrderFacts:
    case_no: str
    order_version: int
    contracted_service_days: int
    service_hours_per_day: int
    actual_start_date: date | None
    service_started: bool
    service_data_locked: bool

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH
        )
        require_nonnegative_integer(self.order_version, "order version")
        require_positive_integer(
            self.contracted_service_days, "contracted service days"
        )
        require_positive_integer(
            self.service_hours_per_day, "service hours per day"
        )
        _require_optional_date(self.actual_start_date, "actual start date")
        if not isinstance(self.service_started, bool):
            raise TypeError("service started must be bool")
        if self.service_started and self.actual_start_date is None:
            raise ValueError("service start requires an actual start date")
        if not isinstance(self.service_data_locked, bool):
            raise TypeError("service data locked must be bool")


@dataclass(frozen=True, slots=True)
class CancellationAssignmentFacts:
    assignment_id: int
    staff_id: int
    sequence: int
    service_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        require_positive_integer(self.staff_id, "staff id")
        require_positive_integer(self.sequence, "assignment sequence")
        _validate_dates(self.service_dates, "assignment service dates")


@dataclass(frozen=True, slots=True)
class ConfirmedServiceDay:
    service_date: date
    staff_id: int
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_date(self.service_date, "confirmed service date")
        require_positive_integer(self.staff_id, "confirmed caregiver id")
        if self.reason is not None:
            require_canonical_text(
                self.reason, "service-day reason", _REASON_MAXIMUM_LENGTH
            )


@dataclass(frozen=True, slots=True)
class CancellationSchedulingFacts:
    case_no: str
    aggregate_version: int
    generation_number: int
    assignments: tuple[CancellationAssignmentFacts, ...]

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH
        )
        require_nonnegative_integer(
            self.aggregate_version, "scheduling aggregate version"
        )
        require_nonnegative_integer(
            self.generation_number, "scheduling generation number"
        )
        if not isinstance(self.assignments, tuple):
            raise TypeError("cancellation assignments must be a tuple")
        if any(
            not isinstance(item, CancellationAssignmentFacts)
            for item in self.assignments
        ):
            raise TypeError("cancellation assignments contain an invalid value")


@dataclass(frozen=True, slots=True)
class CancellationCandidate:
    case_no: str
    expected_order_version: int
    scheduling: SchedulingGenerationCandidate
    cancellation_date: date
    actual_end_date: date | None
    confirmed_service_days: tuple[ConfirmedServiceDay, ...]
    official_service_day_count: int
    official_service_hours: int
    fingerprint: PreviewFingerprint


def build_cancellation_candidate(
    order: CancellationOrderFacts,
    scheduling: CancellationSchedulingFacts,
    cancellation_date: date,
    confirmed_service_days: tuple[ConfirmedServiceDay, ...],
) -> CancellationCandidate:
    _validate_roots(order, scheduling, cancellation_date)
    confirmed = _validate_confirmed_days(
        order, scheduling, cancellation_date, confirmed_service_days
    )
    assignments = _build_assignments(order, scheduling, confirmed)
    generation = _generation_candidate(scheduling, assignments)
    return _candidate(order, generation, cancellation_date, confirmed)


def _validate_roots(order, scheduling, cancellation_date) -> None:
    _require_date(cancellation_date, "cancellation date")
    if order.case_no != scheduling.case_no:
        raise ValueError("cancellation_case_mismatch")
    _validate_existing_assignments(scheduling.assignments)


# Kept cohesive because all checks protect one canonical daily ownership set.
def _validate_confirmed_days(order, scheduling, cancellation_date, values):
    if not isinstance(values, tuple):
        raise TypeError("confirmed service days must be a tuple")
    dates = tuple(item.service_date for item in values)
    if dates != tuple(sorted(set(dates))):
        raise CancellationCandidateError(
            CancellationBlocker.SERVICE_OWNERSHIP_CONFLICT
        )
    _validate_service_day_count(order, len(values))
    if not order.service_started and values:
        raise CancellationCandidateError(
            CancellationBlocker.SERVICE_START_FACT_INCONSISTENT
        )
    if order.service_started and not values:
        raise CancellationCandidateError(
            CancellationBlocker.ACTUAL_SERVICE_FACTS_REQUIRED
        )
    existing_owners = _existing_owner_by_date(scheduling.assignments)
    for item in values:
        _validate_confirmed_day(
            order, cancellation_date, item, existing_owners
        )
    return values


def _validate_service_day_count(order, confirmed_count) -> None:
    contracted = order.contracted_service_days
    if order.service_data_locked and confirmed_count < contracted:
        raise CancellationCandidateError(
            CancellationBlocker.SERVICE_DATA_LOCKED_INCONSISTENT
        )
    if confirmed_count > contracted:
        raise CancellationCandidateError(
            CancellationBlocker.SERVICE_DAYS_EXCEED_CONTRACT
        )
    if confirmed_count == contracted:
        raise CancellationCandidateError(CancellationBlocker.AFTER_FULL_SERVICE)


def _validate_confirmed_day(order, cancellation_date, item, existing_owners):
    if item.service_date > cancellation_date:
        raise CancellationCandidateError(
            CancellationBlocker.SERVICE_DATE_IN_FUTURE
        )
    if (
        order.actual_start_date is not None
        and item.service_date < order.actual_start_date
    ):
        raise CancellationCandidateError(
            CancellationBlocker.SERVICE_DATE_BEFORE_ACTUAL_START
        )
    if existing_owners.get(item.service_date) == item.staff_id:
        return
    if item.reason is None:
        raise CancellationCandidateError(
            CancellationBlocker.SERVICE_DAY_REASON_REQUIRED
        )


def _validate_existing_assignments(assignments) -> None:
    sequences = tuple(item.sequence for item in assignments)
    if sequences != tuple(range(1, len(assignments) + 1)):
        raise ValueError("cancellation_assignment_sequences_invalid")
    _existing_owner_by_date(assignments)


def _existing_owner_by_date(assignments):
    owners: dict[date, int] = {}
    for assignment in assignments:
        for service_date in assignment.service_dates:
            if service_date in owners:
                raise CancellationCandidateError(
                    CancellationBlocker.SERVICE_OWNERSHIP_CONFLICT
                )
            owners[service_date] = assignment.staff_id
    return owners


def _build_assignments(order, scheduling, confirmed):
    owner_groups = _owner_groups(confirmed)
    return tuple(
        _assignment_candidate(order, scheduling, group, sequence)
        for sequence, group in enumerate(owner_groups, start=1)
    )


def _owner_groups(confirmed):
    groups: dict[int, list[ConfirmedServiceDay]] = {}
    for item in confirmed:
        groups.setdefault(item.staff_id, []).append(item)
    return tuple(
        tuple(group)
        for group in sorted(groups.values(), key=lambda value: value[0].service_date)
    )


def _assignment_candidate(order, scheduling, run, sequence):
    service_dates = tuple(item.service_date for item in run)
    source_ids = _source_assignment_ids(scheduling.assignments, service_dates)
    primary_source = _primary_source_id(
        scheduling.assignments, run[0].staff_id, source_ids
    )
    lineage_ids = _lineage_ids(source_ids, primary_source)
    return AssignmentCandidate(
        candidate_key=f"{order.case_no}:g{scheduling.generation_number + 1}:a{sequence}",
        source_assignment_id=primary_source,
        staff_id=run[0].staff_id,
        sequence=sequence,
        assigned_start_date=service_dates[0],
        assigned_end_date=service_dates[-1],
        service_dates=service_dates,
        actual_hours=len(service_dates) * order.service_hours_per_day,
        lineage_source_assignment_ids=lineage_ids,
    )


def _source_assignment_ids(assignments, service_dates):
    dates = set(service_dates)
    return tuple(
        sorted(
            {
                assignment.assignment_id
                for assignment in assignments
                if dates.intersection(assignment.service_dates)
            }
        )
    )


def _primary_source_id(assignments, staff_id, source_ids):
    matching = tuple(
        item.assignment_id for item in assignments if item.staff_id == staff_id
    )
    if matching:
        return matching[0]
    if source_ids:
        return source_ids[0]
    return None


def _lineage_ids(source_ids, primary_source):
    values = set(source_ids)
    if primary_source is not None:
        values.add(primary_source)
    return tuple(sorted(values))


def _generation_candidate(scheduling, assignments):
    return SchedulingGenerationCandidate(
        case_no=scheduling.case_no,
        generation_number=scheduling.generation_number + 1,
        expected_aggregate_version=scheduling.aggregate_version,
        resulting_aggregate_version=scheduling.aggregate_version + 1,
        cancelled_assignment_ids=tuple(
            item.assignment_id for item in scheduling.assignments
        ),
        assignments=assignments,
        buffers=(),
    )


def _candidate(order, generation, cancellation_date, confirmed):
    service_dates = tuple(item.service_date for item in confirmed)
    fingerprint = fingerprint_payload(
        _fingerprint_payload(order, generation, cancellation_date, confirmed)
    )
    return CancellationCandidate(
        order.case_no,
        order.order_version,
        generation,
        cancellation_date,
        service_dates[-1] if service_dates else None,
        confirmed,
        len(service_dates),
        len(service_dates) * order.service_hours_per_day,
        fingerprint,
    )


def _fingerprint_payload(order, generation, cancellation_date, confirmed):
    return {
        "case_no": order.case_no,
        "order_version": order.order_version,
        "contracted_service_days": order.contracted_service_days,
        "service_hours_per_day": order.service_hours_per_day,
        "actual_start_date": _iso_date(order.actual_start_date),
        "scheduling_version": generation.expected_aggregate_version,
        "source_generation": generation.generation_number - 1,
        "cancellation_date": cancellation_date.isoformat(),
        "confirmed_service_days": tuple(
            {
                "service_date": item.service_date.isoformat(),
                "staff_id": item.staff_id,
                "reason": item.reason,
            }
            for item in confirmed
        ),
    }


def _validate_dates(values, field_name) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    if any(not _is_date(value) for value in values):
        raise TypeError(f"{field_name} must contain dates")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be sorted and unique")


def _require_optional_date(value, field_name) -> None:
    if value is not None:
        _require_date(value, field_name)


def _require_date(value, field_name) -> None:
    if not _is_date(value):
        raise TypeError(f"{field_name} must be a date")


def _is_date(value) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _iso_date(value) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "CancellationAssignmentFacts",
    "CancellationBlocker",
    "CancellationCandidate",
    "CancellationCandidateError",
    "CancellationOrderFacts",
    "CancellationSchedulingFacts",
    "ConfirmedServiceDay",
    "build_cancellation_candidate",
]

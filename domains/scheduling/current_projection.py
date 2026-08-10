"""Pure current Scheduling calendar, lifecycle, and occupancy projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from domains.orders.terms import ServiceTimeTerms
from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_BUFFER_DAY_COUNT = 7
_MAXIMUM_QUERY_DAY_COUNT = 62
_CASE_NUMBER_MAXIMUM_LENGTH = 50


class AssignmentLifecycleStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"


class SchedulingOccupancyKind(StrEnum):
    OFFICIAL_WORKDAY = "official_workday"
    ASSIGNMENT_REST = "assignment_rest"
    ASSIGNMENT_BUFFER = "assignment_buffer"
    WAITING_DEPOSIT_SERVICE = "waiting_deposit_service"
    WAITING_DEPOSIT_BUFFER = "waiting_deposit_buffer"


class SchedulingCurrentErrorCode(StrEnum):
    INVALID_QUERY = "invalid_scheduling_query"
    DATA_INTEGRITY = "scheduling_data_integrity_violation"
    OCCUPANCY_CONFLICT = "staff_occupancy_conflict"


class SchedulingCurrentDomainError(ValueError):
    def __init__(
        self,
        code: SchedulingCurrentErrorCode,
        blockers: tuple[str, ...] = (),
    ) -> None:
        self.code = code
        self.blockers = blockers or (code.value,)
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class EffectiveAssignmentCurrentFact:
    assignment_id: int
    case_no: str
    generation_id: int
    scheduling_version: int
    staff_id: int
    assigned_start_date: date
    assigned_end_date: date
    official_service_dates: tuple[date, ...]
    active_buffer_dates: tuple[date, ...]
    service_hours_per_day: int
    service_time_terms: ServiceTimeTerms

    def __post_init__(self) -> None:
        _validate_assignment_identities(self)
        _validate_assignment_dates(self)
        _validate_assignment_service_facts(self)


@dataclass(frozen=True, slots=True)
class StoredEffectiveOccupancyFact:
    staff_id: int
    occupancy_date: date
    generation_id: int
    assignment_id: int
    occupancy_kind: str

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "occupancy staff id")
        require_positive_integer(self.generation_id, "occupancy generation id")
        require_positive_integer(self.assignment_id, "occupancy assignment id")
        _require_date(self.occupancy_date, "occupancy date")
        if self.occupancy_kind not in {"assignment_interval", "buffer"}:
            raise ValueError("stored occupancy kind is invalid")


@dataclass(frozen=True, slots=True)
class WaitingDepositLockCurrentFact:
    lock_id: int
    segment_id: int
    case_no: str
    staff_id: int
    assigned_start_date: date
    assigned_end_date: date
    locked_service_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.lock_id, "waiting lock id")
        require_positive_integer(self.segment_id, "waiting segment id")
        require_canonical_text(
            self.case_no,
            "waiting lock case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        require_positive_integer(self.staff_id, "waiting lock staff id")
        _validate_waiting_lock_dates(self)


@dataclass(frozen=True, slots=True)
class SchedulingCurrentFacts:
    staff_id: int
    assignments: tuple[EffectiveAssignmentCurrentFact, ...]
    stored_occupancy: tuple[StoredEffectiveOccupancyFact, ...]
    waiting_locks: tuple[WaitingDepositLockCurrentFact, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "staff id")
        _validate_fact_tuple(
            self.assignments,
            EffectiveAssignmentCurrentFact,
            "effective assignments",
        )
        _validate_fact_tuple(
            self.stored_occupancy,
            StoredEffectiveOccupancyFact,
            "stored occupancy",
        )
        _validate_fact_tuple(
            self.waiting_locks,
            WaitingDepositLockCurrentFact,
            "waiting locks",
        )
        _validate_staff_ownership(self)


@dataclass(frozen=True, slots=True)
class AssignmentCurrentProjection:
    assignment_id: int
    case_no: str
    generation_id: int
    scheduling_version: int
    staff_id: int
    status: AssignmentLifecycleStatus
    assigned_start_date: date
    assigned_end_date: date
    first_service_at: datetime
    completion_at: datetime
    official_service_day_count: int
    actual_hours: int


@dataclass(frozen=True, slots=True)
class SchedulingDayEntry:
    occupancy_kind: SchedulingOccupancyKind
    case_no: str
    assignment_id: int | None = None
    assignment_status: AssignmentLifecycleStatus | None = None
    lock_id: int | None = None
    segment_id: int | None = None


@dataclass(frozen=True, slots=True)
class SchedulingCurrentDay:
    calendar_date: date
    available: bool
    entries: tuple[SchedulingDayEntry, ...]


@dataclass(frozen=True, slots=True)
class SchedulingCurrentProjection:
    staff_id: int
    range_start: date
    range_end: date
    evaluated_at: datetime
    assignments: tuple[AssignmentCurrentProjection, ...]
    days: tuple[SchedulingCurrentDay, ...]
    case_versions: tuple[tuple[str, int], ...]
    projection_token: PreviewFingerprint


# The typed boundary stays explicit so callers cannot bypass projection inputs.
def build_scheduling_current_projection(
    facts: SchedulingCurrentFacts,
    range_start: date,
    range_end: date,
    evaluated_at: datetime,
) -> SchedulingCurrentProjection:
    query_dates = _validate_query_range(range_start, range_end)
    _validate_evaluation_instant(evaluated_at)
    _validate_stored_occupancy(facts)
    assignments = _project_assignments(facts.assignments, evaluated_at)
    days = _project_days(facts, assignments, query_dates)
    case_versions = _case_versions(facts.assignments)
    token = _projection_token(facts, assignments, days, case_versions)
    return _projection_result(
        facts,
        range_start,
        range_end,
        evaluated_at,
        assignments,
        days,
        case_versions,
        token,
    )


def _projection_result(
    facts,
    range_start,
    range_end,
    evaluated_at,
    assignments,
    days,
    case_versions,
    token,
):
    return SchedulingCurrentProjection(
        facts.staff_id,
        range_start,
        range_end,
        evaluated_at,
        assignments,
        days,
        case_versions,
        token,
    )


def _project_days(facts, assignments, query_dates):
    status_by_assignment = {
        item.assignment_id: item.status for item in assignments
    }
    entries_by_date = _build_entries(facts, status_by_assignment)
    return tuple(
        SchedulingCurrentDay(
            calendar_date=value,
            available=value not in entries_by_date,
            entries=entries_by_date.get(value, ()),
        )
        for value in query_dates
    )


def project_assignment_status(
    assignment: EffectiveAssignmentCurrentFact,
    evaluated_at: datetime,
) -> AssignmentLifecycleStatus:
    _validate_evaluation_instant(evaluated_at)
    first_service_at = _first_service_at(assignment)
    if evaluated_at < first_service_at:
        return AssignmentLifecycleStatus.PLANNED
    if evaluated_at < _completion_at(assignment):
        return AssignmentLifecycleStatus.ACTIVE
    return AssignmentLifecycleStatus.COMPLETED


def _project_assignments(assignments, evaluated_at):
    return tuple(
        _project_assignment(assignment, evaluated_at)
        for assignment in sorted(
            assignments,
            key=lambda item: (item.case_no, item.assignment_id),
        )
    )


def _project_assignment(assignment, evaluated_at):
    service_day_count = len(assignment.official_service_dates)
    return AssignmentCurrentProjection(
        assignment.assignment_id,
        assignment.case_no,
        assignment.generation_id,
        assignment.scheduling_version,
        assignment.staff_id,
        project_assignment_status(assignment, evaluated_at),
        assignment.assigned_start_date,
        assignment.assigned_end_date,
        _first_service_at(assignment),
        _completion_at(assignment),
        service_day_count,
        service_day_count * assignment.service_hours_per_day,
    )


def _build_entries(facts, status_by_assignment):
    entries: dict[date, list[SchedulingDayEntry]] = {}
    occupied_dates: dict[date, SchedulingDayEntry] = {}
    for assignment in facts.assignments:
        _append_assignment_entries(
            entries,
            occupied_dates,
            assignment,
            status_by_assignment[assignment.assignment_id],
        )
    for waiting_lock in facts.waiting_locks:
        _append_waiting_lock_entries(entries, occupied_dates, waiting_lock)
    return {
        key: tuple(sorted(value, key=_entry_sort_key))
        for key, value in entries.items()
    }


def _append_assignment_entries(
    entries,
    occupied_dates,
    assignment,
    assignment_status,
):
    _append_assignment_interval_entries(
        entries,
        occupied_dates,
        assignment,
        assignment_status,
    )
    _append_assignment_buffer_entries(
        entries,
        occupied_dates,
        assignment,
        assignment_status,
    )


def _append_assignment_interval_entries(
    entries,
    occupied_dates,
    assignment,
    assignment_status,
):
    official_dates = set(assignment.official_service_dates)
    for occupied_date in _inclusive_dates(
        assignment.assigned_start_date,
        assignment.assigned_end_date,
    ):
        _append_assignment_interval_entry(
            entries,
            occupied_dates,
            assignment,
            assignment_status,
            occupied_date,
            official_dates,
        )


def _append_assignment_buffer_entries(
    entries,
    occupied_dates,
    assignment,
    assignment_status,
):
    for buffer_date in assignment.active_buffer_dates:
        _append_assignment_buffer_entry(
            entries,
            occupied_dates,
            assignment,
            assignment_status,
            buffer_date,
        )


def _append_assignment_interval_entry(
    entries,
    occupied_dates,
    assignment,
    assignment_status,
    occupied_date,
    official_dates,
):
    kind = (
        SchedulingOccupancyKind.OFFICIAL_WORKDAY
        if occupied_date in official_dates
        else SchedulingOccupancyKind.ASSIGNMENT_REST
    )
    entry = SchedulingDayEntry(
        kind,
        assignment.case_no,
        assignment_id=assignment.assignment_id,
        assignment_status=assignment_status,
    )
    _claim_entry(entries, occupied_dates, occupied_date, entry)


def _append_assignment_buffer_entry(
    entries,
    occupied_dates,
    assignment,
    assignment_status,
    buffer_date,
):
    entry = SchedulingDayEntry(
        SchedulingOccupancyKind.ASSIGNMENT_BUFFER,
        assignment.case_no,
        assignment_id=assignment.assignment_id,
        assignment_status=assignment_status,
    )
    _claim_entry(entries, occupied_dates, buffer_date, entry)


def _append_waiting_lock_entries(entries, occupied_dates, waiting_lock):
    for lock_date in waiting_lock.locked_service_dates:
        entry = SchedulingDayEntry(
            SchedulingOccupancyKind.WAITING_DEPOSIT_SERVICE,
            waiting_lock.case_no,
            lock_id=waiting_lock.lock_id,
            segment_id=waiting_lock.segment_id,
        )
        _claim_entry(entries, occupied_dates, lock_date, entry)
    for buffer_date in _expected_buffer_dates(
        waiting_lock.assigned_end_date
    ):
        entry = SchedulingDayEntry(
            SchedulingOccupancyKind.WAITING_DEPOSIT_BUFFER,
            waiting_lock.case_no,
            lock_id=waiting_lock.lock_id,
            segment_id=waiting_lock.segment_id,
        )
        _claim_entry(entries, occupied_dates, buffer_date, entry)


def _claim_entry(entries, occupied_dates, occupied_date, entry):
    existing = occupied_dates.get(occupied_date)
    if existing is not None:
        blockers = tuple(
            sorted(
                {
                    f"{existing.case_no}:{existing.occupancy_kind.value}",
                    f"{entry.case_no}:{entry.occupancy_kind.value}",
                }
            )
        )
        raise SchedulingCurrentDomainError(
            SchedulingCurrentErrorCode.OCCUPANCY_CONFLICT,
            blockers,
        )
    occupied_dates[occupied_date] = entry
    entries.setdefault(occupied_date, []).append(entry)


def _validate_stored_occupancy(facts):
    expected = _expected_occupancy_set(facts.assignments)
    actual = _stored_occupancy_set(facts.stored_occupancy)
    if len(actual) != len(facts.stored_occupancy) or actual != expected:
        raise SchedulingCurrentDomainError(
            SchedulingCurrentErrorCode.DATA_INTEGRITY,
            ("effective occupancy does not match assignment and buffer roots",),
        )


def _expected_occupancy_set(assignments):
    return {
        identity
        for assignment in assignments
        for identity in _expected_occupancy_identities(assignment)
    }


def _stored_occupancy_set(stored_occupancy):
    return {
        (
            item.staff_id,
            item.occupancy_date,
            item.generation_id,
            item.assignment_id,
            item.occupancy_kind,
        )
        for item in stored_occupancy
    }


def _expected_occupancy_identities(assignment):
    return (
        *_assignment_interval_occupancy(assignment),
        *_assignment_buffer_occupancy(assignment),
    )


def _assignment_interval_occupancy(assignment):
    return (
        (
            assignment.staff_id,
            value,
            assignment.generation_id,
            assignment.assignment_id,
            "assignment_interval",
        )
        for value in _inclusive_dates(
            assignment.assigned_start_date,
            assignment.assigned_end_date,
        )
    )


def _assignment_buffer_occupancy(assignment):
    return (
        (
            assignment.staff_id,
            value,
            assignment.generation_id,
            assignment.assignment_id,
            "buffer",
        )
        for value in assignment.active_buffer_dates
    )


def _projection_token(facts, assignments, days, case_versions):
    payload = {
        "contract_version": "scheduling-current-v1",
        "staff_id": facts.staff_id,
        "case_versions": case_versions,
        "assignments": tuple(_assignment_payload(item) for item in assignments),
        "days": tuple(_day_payload(item) for item in days),
        "waiting_locks": tuple(
            _waiting_lock_payload(item)
            for item in sorted(
                facts.waiting_locks,
                key=lambda value: (value.lock_id, value.segment_id),
            )
        ),
    }
    return fingerprint_payload(payload)


def _assignment_payload(item):
    return {
        "assignment_id": item.assignment_id,
        "case_no": item.case_no,
        "generation_id": item.generation_id,
        "scheduling_version": item.scheduling_version,
        "status": item.status.value,
        "assigned_start_date": item.assigned_start_date.isoformat(),
        "assigned_end_date": item.assigned_end_date.isoformat(),
        "first_service_at": item.first_service_at.isoformat(),
        "completion_at": item.completion_at.isoformat(),
        "official_service_day_count": item.official_service_day_count,
        "actual_hours": item.actual_hours,
    }


def _day_payload(item):
    return {
        "calendar_date": item.calendar_date.isoformat(),
        "available": item.available,
        "entries": tuple(
            {
                "occupancy_kind": entry.occupancy_kind.value,
                "case_no": entry.case_no,
                "assignment_id": entry.assignment_id,
                "assignment_status": (
                    entry.assignment_status.value
                    if entry.assignment_status is not None
                    else None
                ),
                "lock_id": entry.lock_id,
                "segment_id": entry.segment_id,
            }
            for entry in item.entries
        ),
    }


def _waiting_lock_payload(item):
    return {
        "lock_id": item.lock_id,
        "segment_id": item.segment_id,
        "case_no": item.case_no,
        "staff_id": item.staff_id,
        "assigned_start_date": item.assigned_start_date.isoformat(),
        "assigned_end_date": item.assigned_end_date.isoformat(),
        "locked_service_dates": tuple(
            value.isoformat() for value in item.locked_service_dates
        ),
    }


def _case_versions(assignments):
    versions: dict[str, int] = {}
    for assignment in assignments:
        existing = versions.setdefault(
            assignment.case_no,
            assignment.scheduling_version,
        )
        if existing != assignment.scheduling_version:
            raise SchedulingCurrentDomainError(
                SchedulingCurrentErrorCode.DATA_INTEGRITY,
                ("one case has multiple current scheduling versions",),
            )
    return tuple(sorted(versions.items()))


def _validate_assignment_identities(assignment):
    require_positive_integer(assignment.assignment_id, "assignment id")
    require_canonical_text(
        assignment.case_no,
        "case number",
        _CASE_NUMBER_MAXIMUM_LENGTH,
    )
    require_positive_integer(assignment.generation_id, "generation id")
    require_nonnegative_integer(
        assignment.scheduling_version,
        "scheduling version",
    )
    require_positive_integer(assignment.staff_id, "assignment staff id")


def _validate_assignment_dates(assignment):
    _require_date(assignment.assigned_start_date, "assigned start date")
    _require_date(assignment.assigned_end_date, "assigned end date")
    if assignment.assigned_end_date < assignment.assigned_start_date:
        raise ValueError("assignment interval is inverted")
    service_dates = assignment.official_service_dates
    if not service_dates or service_dates != tuple(sorted(set(service_dates))):
        raise ValueError("official service dates must be canonical and nonempty")
    interval_dates = set(
        _inclusive_dates(
            assignment.assigned_start_date,
            assignment.assigned_end_date,
        )
    )
    if not set(service_dates).issubset(interval_dates):
        raise ValueError("official service date is outside assignment interval")


def _validate_assignment_service_facts(assignment):
    require_positive_integer(
        assignment.service_hours_per_day,
        "service hours per day",
    )
    if not isinstance(assignment.service_time_terms, ServiceTimeTerms):
        raise TypeError("service time terms are invalid")
    if not assignment.service_time_terms.complete:
        raise ValueError("service_time_terms_incomplete")
    buffers = assignment.active_buffer_dates
    if buffers and buffers != _expected_buffer_dates(
        assignment.assigned_end_date
    ):
        raise ValueError("active assignment buffer must contain exactly seven days")


def _validate_waiting_lock_dates(waiting_lock):
    _require_date(waiting_lock.assigned_start_date, "lock start date")
    _require_date(waiting_lock.assigned_end_date, "lock end date")
    if waiting_lock.assigned_end_date < waiting_lock.assigned_start_date:
        raise ValueError("waiting lock interval is inverted")
    expected = _inclusive_dates(
        waiting_lock.assigned_start_date,
        waiting_lock.assigned_end_date,
    )
    if waiting_lock.locked_service_dates != expected:
        raise ValueError("waiting lock must cover its full service interval")


def _validate_staff_ownership(facts):
    staff_ids = {
        item.staff_id
        for item in (*facts.assignments, *facts.stored_occupancy, *facts.waiting_locks)
    }
    if staff_ids and staff_ids != {facts.staff_id}:
        raise ValueError("current scheduling facts mix staff identities")


def _validate_fact_tuple(values, expected_type, label):
    if not isinstance(values, tuple):
        raise TypeError(f"{label} must be a tuple")
    if any(not isinstance(value, expected_type) for value in values):
        raise TypeError(f"{label} contain an invalid value")


def _validate_query_range(range_start, range_end):
    _require_date(range_start, "range start")
    _require_date(range_end, "range end")
    if range_end < range_start:
        raise SchedulingCurrentDomainError(
            SchedulingCurrentErrorCode.INVALID_QUERY
        )
    values = _inclusive_dates(range_start, range_end)
    if len(values) > _MAXIMUM_QUERY_DAY_COUNT:
        raise SchedulingCurrentDomainError(
            SchedulingCurrentErrorCode.INVALID_QUERY,
            ("query range exceeds 62 days",),
        )
    return values


def _validate_evaluation_instant(value):
    if not isinstance(value, datetime):
        raise TypeError("evaluation instant must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evaluation instant must be timezone-aware")
    if getattr(value.tzinfo, "key", None) != TAIPEI_TIME_ZONE.key:
        raise ValueError("evaluation instant must use Asia/Taipei")


def _first_service_at(assignment):
    start_time = assignment.service_time_terms.start_time
    return datetime.combine(
        assignment.official_service_dates[0],
        start_time,
        tzinfo=TAIPEI_TIME_ZONE,
    )


def _completion_at(assignment):
    return assignment.service_time_terms.completion_instant(
        assignment.official_service_dates[-1]
    )


def _expected_buffer_dates(end_date):
    return tuple(
        end_date + timedelta(days=offset)
        for offset in range(1, _BUFFER_DAY_COUNT + 1)
    )


def _inclusive_dates(start_date, end_date):
    return tuple(
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    )


def _entry_sort_key(entry):
    return (
        entry.occupancy_kind.value,
        entry.case_no,
        entry.assignment_id or 0,
        entry.lock_id or 0,
    )


def _require_date(value, field):
    if type(value) is not date:
        raise TypeError(f"{field} must be a date")


__all__ = [
    "AssignmentCurrentProjection",
    "AssignmentLifecycleStatus",
    "EffectiveAssignmentCurrentFact",
    "SchedulingCurrentDay",
    "SchedulingCurrentDomainError",
    "SchedulingCurrentErrorCode",
    "SchedulingCurrentFacts",
    "SchedulingCurrentProjection",
    "SchedulingDayEntry",
    "SchedulingOccupancyKind",
    "StoredEffectiveOccupancyFact",
    "WaitingDepositLockCurrentFact",
    "build_scheduling_current_projection",
    "project_assignment_status",
]

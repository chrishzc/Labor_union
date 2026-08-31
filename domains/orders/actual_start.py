"""Pure Actual Start roots and deterministic shift candidate builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from domains.orders.terms import ServiceTimeTerms
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

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_POST_SERVICE_BUFFER_DAYS = 7


class ActualStartCandidateKind(StrEnum):
    FIRST_CONFIRMATION = "first_confirmation"
    CORRECTION = "correction"


class ActualStartReconfirmationState(StrEnum):
    NOT_REQUIRED = "not_required"
    ACTIVE = "active"
    CLEARED = "cleared"


class ActualStartReconfirmationAction(StrEnum):
    NO_OP = "no_op"
    CONFIRM_ACTIVE = "confirm_active"


class ActualStartBlocker(StrEnum):
    SERVICE_DATA_LOCKED = "service_data_locked"
    SERVICE_TIME_TERMS_INCOMPLETE = "service_time_terms_incomplete"
    SCHEDULING_ASSIGNMENTS_REQUIRED = "scheduling_assignments_required"
    SCHEDULING_CASE_MISMATCH = "scheduling_case_mismatch"
    SCHEDULING_ROOT_MISMATCH = "scheduling_root_mismatch"
    SCHEDULING_SERVICE_DATES_INVALID = "scheduling_service_dates_invalid"
    RECONFIRMATION_PROJECTION_MISSING = (
        "actual_start_reconfirmation_projection_missing"
    )
    RECONFIRMATION_DEPOSIT_UNSETTLED = (
        "actual_start_reconfirmation_deposit_unsettled"
    )
    RECONFIRMATION_SETTLEMENT_IDENTITY_MISSING = (
        "actual_start_reconfirmation_settlement_identity_missing"
    )
    RECONFIRMATION_SETTLEMENT_IDENTITY_MISMATCH = (
        "actual_start_reconfirmation_settlement_identity_mismatch"
    )


class ActualStartCandidateError(ValueError):
    def __init__(self, blocker: ActualStartBlocker) -> None:
        self.blocker = blocker
        super().__init__(blocker.value)


@dataclass(frozen=True, slots=True)
class ActualStartReconfirmationFacts:
    state: ActualStartReconfirmationState
    required_settlement_identity: PreviewFingerprint | None
    current_settlement_identity: PreviewFingerprint | None
    deposit_settled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.state, ActualStartReconfirmationState):
            raise TypeError("actual start reconfirmation state is invalid")
        _validate_optional_fingerprint(
            self.required_settlement_identity,
            "required settlement identity",
        )
        _validate_optional_fingerprint(
            self.current_settlement_identity,
            "current settlement identity",
        )
        if not isinstance(self.deposit_settled, bool):
            raise TypeError("deposit settled must be bool")


@dataclass(frozen=True, slots=True)
class ActualStartReconfirmationCandidate:
    state: ActualStartReconfirmationState
    action: ActualStartReconfirmationAction
    settlement_identity: PreviewFingerprint | None
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ActualStartOrderFacts:
    case_no: str
    aggregate_version: int
    actual_start_date: date | None
    service_data_locked: bool
    service_time: ServiceTimeTerms

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no,
            "case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        require_nonnegative_integer(self.aggregate_version, "order version")
        if self.actual_start_date is not None:
            _require_date(self.actual_start_date, "actual start date")
        if not isinstance(self.service_data_locked, bool):
            raise TypeError("service data locked must be bool")
        if not isinstance(self.service_time, ServiceTimeTerms):
            raise TypeError("service time must be ServiceTimeTerms")


@dataclass(frozen=True, slots=True)
class ActualStartAssignmentFacts:
    assignment_id: int
    staff_id: int
    sequence: int
    assigned_start_date: date
    assigned_end_date: date
    service_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        require_positive_integer(self.staff_id, "staff id")
        require_positive_integer(self.sequence, "assignment sequence")
        _require_date(self.assigned_start_date, "assigned start date")
        _require_date(self.assigned_end_date, "assigned end date")
        if self.assigned_end_date < self.assigned_start_date:
            raise ValueError("assigned interval is inverted")
        _validate_assignment_service_dates(self)


@dataclass(frozen=True, slots=True)
class ActualStartSchedulingFacts:
    case_no: str
    aggregate_version: int
    generation_number: int
    root_date: date
    assignments: tuple[ActualStartAssignmentFacts, ...]

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
        _require_date(self.root_date, "scheduling root date")
        _validate_scheduling_assignments_type(self.assignments)


def _validate_scheduling_assignments_type(
    assignments: object,
) -> None:
    if not isinstance(assignments, tuple):
        raise TypeError("scheduling assignments must be a tuple")
    if any(
        not isinstance(assignment, ActualStartAssignmentFacts)
        for assignment in assignments
    ):
        raise TypeError("scheduling assignments contain an invalid value")


@dataclass(frozen=True, slots=True)
class ActualStartAssignmentCandidate:
    source_assignment_id: int
    staff_id: int
    sequence: int
    assigned_start_date: date
    assigned_end_date: date
    service_dates: tuple[date, ...]
    actual_hours: int


@dataclass(frozen=True, slots=True)
class ActualStartCandidate:
    case_no: str
    kind: ActualStartCandidateKind
    expected_order_version: int
    expected_scheduling_version: int
    source_generation_number: int
    original_actual_start_date: date | None
    original_scheduling_root_date: date
    new_actual_start_date: date
    shift_days: int
    assignments: tuple[ActualStartAssignmentCandidate, ...]
    official_service_dates: tuple[date, ...]
    actual_end_date: date
    fingerprint: PreviewFingerprint


def build_actual_start_reconfirmation_candidate(
    facts: ActualStartReconfirmationFacts | None,
) -> ActualStartReconfirmationCandidate:
    if facts is None:
        raise ActualStartCandidateError(
            ActualStartBlocker.RECONFIRMATION_PROJECTION_MISSING
        )
    if facts.state is not ActualStartReconfirmationState.ACTIVE:
        return _reconfirmation_candidate(
            facts,
            ActualStartReconfirmationAction.NO_OP,
            None,
        )
    _validate_active_reconfirmation(facts)
    return _reconfirmation_candidate(
        facts,
        ActualStartReconfirmationAction.CONFIRM_ACTIVE,
        facts.required_settlement_identity,
    )


def build_actual_start_candidate(
    order: ActualStartOrderFacts,
    scheduling: ActualStartSchedulingFacts,
    new_actual_start_date: date,
    service_hours_per_day: int,
    recalculated_service_dates: tuple[date, ...] | None = None,
) -> ActualStartCandidate:
    _validate_candidate_roots(order, scheduling, new_actual_start_date)
    require_positive_integer(service_hours_per_day, "service hours per day")
    shift_days = (new_actual_start_date - scheduling.root_date).days
    assignments = (
        _recalculate_assignments(
            scheduling, recalculated_service_dates, service_hours_per_day
        )
        if recalculated_service_dates is not None
        else _shift_assignments(scheduling, shift_days, service_hours_per_day)
    )
    service_dates = _official_service_dates(assignments)
    return _build_candidate(
        order, scheduling, new_actual_start_date,
        shift_days, assignments, service_dates,
    )


def _validate_active_reconfirmation(
    facts: ActualStartReconfirmationFacts,
) -> None:
    if not facts.deposit_settled:
        raise ActualStartCandidateError(
            ActualStartBlocker.RECONFIRMATION_DEPOSIT_UNSETTLED
        )
    required = facts.required_settlement_identity
    current = facts.current_settlement_identity
    if required is None or current is None:
        raise ActualStartCandidateError(
            ActualStartBlocker.RECONFIRMATION_SETTLEMENT_IDENTITY_MISSING
        )
    if required != current:
        raise ActualStartCandidateError(
            ActualStartBlocker.RECONFIRMATION_SETTLEMENT_IDENTITY_MISMATCH
        )


def _reconfirmation_candidate(
    facts: ActualStartReconfirmationFacts,
    action: ActualStartReconfirmationAction,
    settlement_identity: PreviewFingerprint | None,
) -> ActualStartReconfirmationCandidate:
    payload = _reconfirmation_payload(facts, action)
    return ActualStartReconfirmationCandidate(
        facts.state,
        action,
        settlement_identity,
        fingerprint_payload(payload),
    )


def _reconfirmation_payload(
    facts: ActualStartReconfirmationFacts,
    action: ActualStartReconfirmationAction,
) -> dict[str, object]:
    return {
        "state": facts.state.value,
        "action": action.value,
        "required_settlement_identity": _fingerprint_value(
            facts.required_settlement_identity
        ),
        "current_settlement_identity": _fingerprint_value(
            facts.current_settlement_identity
        ),
        "deposit_settled": facts.deposit_settled,
    }


def to_scheduling_generation_candidate(
    actual_start: ActualStartCandidate,
) -> SchedulingGenerationCandidate:
    generation_number = actual_start.source_generation_number + 1
    assignments = tuple(
        _to_scheduling_assignment(actual_start, assignment, generation_number)
        for assignment in actual_start.assignments
    )
    buffers = tuple(_inactive_buffer(assignment) for assignment in assignments)
    return SchedulingGenerationCandidate(
        case_no=actual_start.case_no,
        generation_number=generation_number,
        expected_aggregate_version=actual_start.expected_scheduling_version,
        resulting_aggregate_version=actual_start.expected_scheduling_version + 1,
        cancelled_assignment_ids=tuple(
            assignment.source_assignment_id for assignment in assignments
        ),
        assignments=assignments,
        buffers=buffers,
    )


def _shift_assignments(
    scheduling: ActualStartSchedulingFacts,
    shift_days: int,
    service_hours_per_day: int,
) -> tuple[ActualStartAssignmentCandidate, ...]:
    return tuple(
        _shift_assignment(assignment, shift_days, service_hours_per_day)
        for assignment in _ordered_assignments(scheduling)
    )


def _to_scheduling_assignment(
    actual_start: ActualStartCandidate,
    assignment: ActualStartAssignmentCandidate,
    generation_number: int,
) -> AssignmentCandidate:
    return AssignmentCandidate(
        candidate_key=(
            f"{actual_start.case_no}:g{generation_number}:a{assignment.sequence}"
        ),
        source_assignment_id=assignment.source_assignment_id,
        staff_id=assignment.staff_id,
        sequence=assignment.sequence,
        assigned_start_date=assignment.assigned_start_date,
        assigned_end_date=assignment.assigned_end_date,
        service_dates=assignment.service_dates,
        actual_hours=assignment.actual_hours,
    )


def _inactive_buffer(assignment: AssignmentCandidate) -> BufferCandidate:
    dates = tuple(
        assignment.assigned_end_date + timedelta(days=offset)
        for offset in range(1, _POST_SERVICE_BUFFER_DAYS + 1)
    )
    return BufferCandidate(
        candidate_key=f"{assignment.candidate_key}:buffer",
        staff_id=assignment.staff_id,
        dates=dates,
        active=False,
    )


def _validate_candidate_roots(
    order: ActualStartOrderFacts,
    scheduling: ActualStartSchedulingFacts,
    new_actual_start_date: date,
) -> None:
    _require_date(new_actual_start_date, "new actual start date")
    if order.service_data_locked:
        raise ActualStartCandidateError(ActualStartBlocker.SERVICE_DATA_LOCKED)
    if order.case_no != scheduling.case_no:
        raise ActualStartCandidateError(ActualStartBlocker.SCHEDULING_CASE_MISMATCH)
    if not scheduling.assignments:
        raise ActualStartCandidateError(
            ActualStartBlocker.SCHEDULING_ASSIGNMENTS_REQUIRED
        )


def _ordered_assignments(
    scheduling: ActualStartSchedulingFacts,
) -> tuple[ActualStartAssignmentFacts, ...]:
    assignments = tuple(
        sorted(scheduling.assignments, key=lambda assignment: assignment.sequence)
    )
    _validate_assignment_identities(assignments)
    if not _first_assignment_starts_at_root(assignments, scheduling.root_date):
        raise ActualStartCandidateError(
            ActualStartBlocker.SCHEDULING_ROOT_MISMATCH
        )
    return assignments


def _first_assignment_starts_at_root(
    assignments: tuple[ActualStartAssignmentFacts, ...],
    root_date: date,
) -> bool:
    first_assignment = assignments[0]
    return (
        first_assignment.assigned_start_date == root_date
        and first_assignment.service_dates[0] == root_date
    )


def _validate_assignment_identities(
    assignments: tuple[ActualStartAssignmentFacts, ...],
) -> None:
    sequences = tuple(assignment.sequence for assignment in assignments)
    assignment_ids = tuple(assignment.assignment_id for assignment in assignments)
    if sequences != tuple(range(1, len(assignments) + 1)):
        raise ActualStartCandidateError(
            ActualStartBlocker.SCHEDULING_SERVICE_DATES_INVALID
        )
    if len(set(assignment_ids)) != len(assignment_ids):
        raise ActualStartCandidateError(
            ActualStartBlocker.SCHEDULING_SERVICE_DATES_INVALID
        )


def _shift_assignment(
    assignment: ActualStartAssignmentFacts,
    shift_days: int,
    service_hours_per_day: int,
) -> ActualStartAssignmentCandidate:
    shift = timedelta(days=shift_days)
    service_dates = tuple(
        service_date + shift for service_date in assignment.service_dates
    )
    return ActualStartAssignmentCandidate(
        source_assignment_id=assignment.assignment_id,
        staff_id=assignment.staff_id,
        sequence=assignment.sequence,
        assigned_start_date=assignment.assigned_start_date + shift,
        assigned_end_date=assignment.assigned_end_date + shift,
        service_dates=service_dates,
        actual_hours=len(service_dates) * service_hours_per_day,
    )


def calculate_service_dates(
    actual_start_date: date,
    service_days: int,
    service_mode: str,
    holiday_dates: tuple[date, ...],
) -> tuple[date, ...]:
    """Calculate official work days from one order's rest mode and holidays."""

    _require_date(actual_start_date, "actual start date")
    require_positive_integer(service_days, "service days")
    if service_mode not in {"週休1日", "週休2日", "連續服務"}:
        raise ValueError("service mode is unsupported")
    if holiday_dates != tuple(sorted(set(holiday_dates))):
        raise ValueError("holiday dates must be canonically ordered")
    if any(type(value) is not date for value in holiday_dates):
        raise TypeError("holiday dates must contain dates")
    rest_weekdays = {
        "週休1日": {6},
        "週休2日": {5, 6},
        "連續服務": set(),
    }[service_mode]
    holidays = set(holiday_dates)
    service_dates: list[date] = []
    current = actual_start_date
    while len(service_dates) < service_days:
        if current.weekday() not in rest_weekdays and current not in holidays:
            service_dates.append(current)
        current += timedelta(days=1)
    return tuple(service_dates)


def _recalculate_assignments(
    scheduling: ActualStartSchedulingFacts,
    service_dates: tuple[date, ...],
    service_hours_per_day: int,
) -> tuple[ActualStartAssignmentCandidate, ...]:
    assignments = _ordered_assignments(scheduling)
    if service_dates != tuple(sorted(set(service_dates))) or not service_dates:
        raise ActualStartCandidateError(
            ActualStartBlocker.SCHEDULING_SERVICE_DATES_INVALID
        )
    expected_count = sum(len(item.service_dates) for item in assignments)
    if len(service_dates) != expected_count:
        raise ActualStartCandidateError(
            ActualStartBlocker.SCHEDULING_SERVICE_DATES_INVALID
        )
    offset = 0
    result: list[ActualStartAssignmentCandidate] = []
    for assignment in assignments:
        count = len(assignment.service_dates)
        assigned_dates = service_dates[offset:offset + count]
        offset += count
        result.append(
            ActualStartAssignmentCandidate(
                source_assignment_id=assignment.assignment_id,
                staff_id=assignment.staff_id,
                sequence=assignment.sequence,
                assigned_start_date=assigned_dates[0],
                assigned_end_date=assigned_dates[-1],
                service_dates=assigned_dates,
                actual_hours=len(assigned_dates) * service_hours_per_day,
            )
        )
    return tuple(result)


def _official_service_dates(
    assignments: tuple[ActualStartAssignmentCandidate, ...],
) -> tuple[date, ...]:
    service_dates = tuple(
        service_date
        for assignment in assignments
        for service_date in assignment.service_dates
    )
    if service_dates != tuple(sorted(set(service_dates))):
        raise ActualStartCandidateError(
            ActualStartBlocker.SCHEDULING_SERVICE_DATES_INVALID
        )
    return service_dates


# Kept cohesive so the fingerprint and returned facts cannot drift.
def _build_candidate(
    order: ActualStartOrderFacts,
    scheduling: ActualStartSchedulingFacts,
    new_actual_start_date: date,
    shift_days: int,
    assignments: tuple[ActualStartAssignmentCandidate, ...],
    service_dates: tuple[date, ...],
) -> ActualStartCandidate:
    kind = _candidate_kind(order.actual_start_date)
    fingerprint = fingerprint_payload(
        _fingerprint_payload(order, scheduling, new_actual_start_date, assignments)
    )
    return ActualStartCandidate(
        order.case_no,
        kind,
        order.aggregate_version,
        scheduling.aggregate_version,
        scheduling.generation_number,
        order.actual_start_date,
        scheduling.root_date,
        new_actual_start_date,
        shift_days,
        assignments,
        service_dates,
        service_dates[-1],
        fingerprint,
    )


def _fingerprint_payload(
    order: ActualStartOrderFacts,
    scheduling: ActualStartSchedulingFacts,
    new_actual_start_date: date,
    assignments: tuple[ActualStartAssignmentCandidate, ...],
) -> dict[str, object]:
    return {
        "case_no": order.case_no,
        "kind": _candidate_kind(order.actual_start_date).value,
        "expected_order_version": order.aggregate_version,
        "expected_scheduling_version": scheduling.aggregate_version,
        "source_generation_number": scheduling.generation_number,
        "original_actual_start_date": _iso_date(order.actual_start_date),
        "original_scheduling_root_date": scheduling.root_date.isoformat(),
        "new_actual_start_date": new_actual_start_date.isoformat(),
        "service_time": order.service_time.canonical_payload(),
        "assignments": tuple(_assignment_payload(item) for item in assignments),
    }


def _assignment_payload(
    assignment: ActualStartAssignmentCandidate,
) -> dict[str, object]:
    return {
        "source_assignment_id": assignment.source_assignment_id,
        "staff_id": assignment.staff_id,
        "sequence": assignment.sequence,
        "assigned_start_date": assignment.assigned_start_date.isoformat(),
        "assigned_end_date": assignment.assigned_end_date.isoformat(),
        "service_dates": tuple(
            service_date.isoformat() for service_date in assignment.service_dates
        ),
        "actual_hours": assignment.actual_hours,
    }


def _validate_assignment_service_dates(
    assignment: ActualStartAssignmentFacts,
) -> None:
    service_dates = assignment.service_dates
    if not isinstance(service_dates, tuple) or not service_dates:
        raise ValueError("assignment service dates must be a nonempty tuple")
    if any(not _is_date(service_date) for service_date in service_dates):
        raise TypeError("assignment service dates must contain dates")
    if service_dates != tuple(sorted(set(service_dates))):
        raise ValueError("assignment service dates must be sorted and unique")
    if any(
        service_date < assignment.assigned_start_date
        or service_date > assignment.assigned_end_date
        for service_date in service_dates
    ):
        raise ValueError("assignment service date is outside its interval")


def _candidate_kind(actual_start_date: date | None) -> ActualStartCandidateKind:
    if actual_start_date is None:
        return ActualStartCandidateKind.FIRST_CONFIRMATION
    return ActualStartCandidateKind.CORRECTION


def _iso_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _fingerprint_value(value: PreviewFingerprint | None) -> str | None:
    if value is None:
        return None
    return value.value


def _validate_optional_fingerprint(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, PreviewFingerprint):
        raise TypeError(f"{field_name} must be PreviewFingerprint")


def _is_date(value: object) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _require_date(value: object, field_name: str) -> None:
    if not _is_date(value):
        raise TypeError(f"{field_name} must be a date")


__all__ = [
    "ActualStartAssignmentCandidate",
    "ActualStartAssignmentFacts",
    "ActualStartBlocker",
    "ActualStartCandidate",
    "ActualStartCandidateError",
    "ActualStartCandidateKind",
    "ActualStartOrderFacts",
    "ActualStartReconfirmationAction",
    "ActualStartReconfirmationCandidate",
    "ActualStartReconfirmationFacts",
    "ActualStartReconfirmationState",
    "ActualStartSchedulingFacts",
    "build_actual_start_candidate",
    "calculate_service_dates",
    "build_actual_start_reconfirmation_candidate",
    "to_scheduling_generation_candidate",
]

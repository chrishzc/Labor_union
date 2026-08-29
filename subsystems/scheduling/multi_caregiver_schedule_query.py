"""Bounded, read-only query contract for multi-caregiver schedule projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_CEILING
from typing import Protocol

from shared_kernel.validation import require_positive_integer


@dataclass(frozen=True, slots=True)
class AssignmentScheduleDay:
    id: int
    case_no: str
    staff_id: int
    assignment_id: int
    work_date: date
    is_work_day: bool
    is_double_pay: bool
    notes: str | None
    is_historical: bool


@dataclass(frozen=True, slots=True)
class AssignmentScheduleAssignment:
    id: int
    case_no: str
    staff_id: int
    status: str
    assigned_start_date: date
    assigned_end_date: date
    planned_hours: Decimal | None
    actual_hours: Decimal | None
    service_hours_per_day: Decimal
    staff_name: str
    client_name: str


@dataclass(frozen=True, slots=True)
class AssignmentScheduleGuard:
    is_cancelled: bool
    has_actual_hours_adjustments: bool
    has_active_staff_payment: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AssignmentScheduleQuery:
    assignment: AssignmentScheduleAssignment
    schedule_days: tuple[AssignmentScheduleDay, ...]
    database_current_date: date
    adjustment_guard: AssignmentScheduleGuard


@dataclass(frozen=True, slots=True)
class StaffAssignmentOption:
    id: int
    case_no: str
    staff_id: int
    status: str
    assigned_start_date: date
    assigned_end_date: date
    order_status: str
    actual_start_date: date | None
    actual_end_date: date | None
    staff_name: str


@dataclass(frozen=True, slots=True)
class CaseAssignment:
    id: int
    case_no: str
    staff_id: int
    status: str
    assigned_start_date: date
    assigned_end_date: date
    original_assigned_start_date: date | None
    original_assigned_end_date: date | None
    planned_hours: Decimal
    actual_hours: Decimal
    service_days: int
    service_hours_per_day: Decimal
    staff_name: str
    actual_service_days: int
    rest_days: int
    substitute_service_days: int
    deferred_leave_days: int
    leave_resolution_days: int
    required_service_days: int
    adjusted_assigned_start_date: date
    adjusted_assigned_end_date: date
    original_scheduled_service_days: int
    makeup_service_days: int


@dataclass(frozen=True, slots=True)
class CaseAssignmentSummary:
    required_service_days: int
    actual_service_days: int
    actual_hours: Decimal
    adjusted_start_date: date
    adjusted_end_date: date
    target_service_days: int
    target_service_hours: Decimal
    has_service_gap: bool
    has_service_overlap: bool
    rest_days: int
    substitute_service_days: int
    deferred_leave_days: int


@dataclass(frozen=True, slots=True)
class CaseAssignmentQuery:
    assignments: tuple[CaseAssignment, ...]
    summary: CaseAssignmentSummary | None


class MultiCaregiverScheduleQueryRepository(Protocol):
    def get_assignment_schedule(self, assignment_id: int) -> AssignmentScheduleQuery: ...

    def list_staff_assignments(self, staff_id: int) -> tuple[StaffAssignmentOption, ...]: ...

    def list_case_assignments(self, case_no: str) -> tuple[CaseAssignment, ...]: ...


class MultiCaregiverScheduleQueryApplication:
    """Scheduling-owned read application; it performs no writes or transactions."""

    def __init__(self, repository: MultiCaregiverScheduleQueryRepository) -> None:
        self._repository = repository

    def get_assignment_schedule(self, assignment_id: int) -> AssignmentScheduleQuery:
        require_positive_integer(assignment_id, "assignment_id")
        return self._repository.get_assignment_schedule(assignment_id)

    def list_staff_assignments(self, staff_id: int) -> tuple[StaffAssignmentOption, ...]:
        require_positive_integer(staff_id, "staff_id")
        return self._repository.list_staff_assignments(staff_id)

    def list_case_assignments(self, case_no: str) -> CaseAssignmentQuery:
        normalized = _case_no(case_no)
        assignments = tuple(self._repository.list_case_assignments(normalized))
        if not assignments:
            return CaseAssignmentQuery((), None)
        service_days = assignments[0].service_days
        hours_per_day = assignments[0].service_hours_per_day
        target_service_hours = Decimal(service_days) * hours_per_day
        actual_service_days = sum(item.actual_service_days for item in assignments)
        actual_hours = sum((item.actual_hours for item in assignments), Decimal("0"))
        return CaseAssignmentQuery(
            assignments,
            CaseAssignmentSummary(
                required_service_days=sum(item.required_service_days for item in assignments),
                actual_service_days=actual_service_days,
                actual_hours=actual_hours,
                adjusted_start_date=min(item.assigned_start_date for item in assignments),
                adjusted_end_date=max(item.assigned_end_date for item in assignments),
                target_service_days=service_days,
                target_service_hours=target_service_hours,
                has_service_gap=(
                    actual_service_days < service_days or actual_hours < target_service_hours
                ),
                has_service_overlap=(
                    actual_service_days > service_days or actual_hours > target_service_hours
                ),
                rest_days=sum(item.rest_days for item in assignments),
                substitute_service_days=sum(item.substitute_service_days for item in assignments),
                deferred_leave_days=sum(item.deferred_leave_days for item in assignments),
            ),
        )


def build_case_assignment(
    *,
    id: int,
    case_no: str,
    staff_id: int,
    status: str,
    assigned_start_date: date,
    assigned_end_date: date,
    original_assigned_start_date: date | None,
    original_assigned_end_date: date | None,
    planned_hours: Decimal,
    actual_hours: Decimal,
    service_days: int,
    service_hours_per_day: Decimal,
    staff_name: str,
    actual_service_days: int,
    rest_days: int,
    substitute_service_days: int,
    deferred_leave_days: int,
    leave_resolution_days: int,
) -> CaseAssignment:
    if assigned_start_date > assigned_end_date:
        raise ValueError("assignment assigned_start_date cannot be after assigned_end_date")
    if not service_hours_per_day.is_finite() or service_hours_per_day <= 0:
        raise ValueError("service_hours_per_day must be positive")
    required_service_days = int(
        (planned_hours / service_hours_per_day).to_integral_value(rounding=ROUND_CEILING)
    )
    original_start = original_assigned_start_date or assigned_start_date
    original_end = original_assigned_end_date or assigned_end_date
    return CaseAssignment(
        id=id,
        case_no=case_no,
        staff_id=staff_id,
        status=status,
        assigned_start_date=assigned_start_date,
        assigned_end_date=assigned_end_date,
        original_assigned_start_date=original_start,
        original_assigned_end_date=original_end,
        planned_hours=planned_hours,
        actual_hours=actual_hours,
        service_days=service_days,
        service_hours_per_day=service_hours_per_day,
        staff_name=staff_name,
        actual_service_days=actual_service_days,
        rest_days=rest_days,
        substitute_service_days=substitute_service_days,
        deferred_leave_days=deferred_leave_days,
        leave_resolution_days=leave_resolution_days,
        required_service_days=required_service_days,
        adjusted_assigned_start_date=assigned_start_date,
        adjusted_assigned_end_date=assigned_end_date,
        original_scheduled_service_days=required_service_days,
        makeup_service_days=deferred_leave_days,
    )


def _case_no(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 50:
        raise ValueError("case_no must be a non-empty string")
    return value.strip()


__all__ = [
    "AssignmentScheduleAssignment",
    "AssignmentScheduleDay",
    "AssignmentScheduleGuard",
    "AssignmentScheduleQuery",
    "CaseAssignment",
    "CaseAssignmentQuery",
    "CaseAssignmentSummary",
    "MultiCaregiverScheduleQueryApplication",
    "MultiCaregiverScheduleQueryRepository",
    "StaffAssignmentOption",
    "build_case_assignment",
]

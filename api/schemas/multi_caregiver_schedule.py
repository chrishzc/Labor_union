"""Typed public views for Scheduling multi-caregiver read endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AssignmentScheduleDayView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    staff_id: int = Field(gt=0)
    assignment_id: int = Field(gt=0)
    work_date: date
    is_work_day: bool
    is_double_pay: bool
    notes: str | None
    is_historical: bool


class AssignmentScheduleAssignmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    staff_id: int = Field(gt=0)
    status: str = Field(min_length=1, max_length=50)
    assigned_start_date: date
    assigned_end_date: date
    planned_hours: Decimal | None
    actual_hours: Decimal | None
    service_hours_per_day: Decimal
    staff_name: str = Field(min_length=1, max_length=200)
    client_name: str = Field(min_length=1, max_length=200)


class AssignmentScheduleGuardView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_cancelled: bool
    has_actual_hours_adjustments: bool
    has_active_staff_payment: bool
    reasons: list[str]


class AssignmentScheduleView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment: AssignmentScheduleAssignmentView
    schedule_days: list[AssignmentScheduleDayView]
    database_current_date: date
    adjustment_guard: AssignmentScheduleGuardView


class CaseAssignmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    case_no: str = Field(min_length=1, max_length=50)
    staff_id: int = Field(gt=0)
    status: str = Field(min_length=1, max_length=50)
    assigned_start_date: date
    assigned_end_date: date
    original_assigned_start_date: date
    original_assigned_end_date: date
    planned_hours: Decimal
    actual_hours: Decimal
    service_days: int = Field(ge=0)
    service_hours_per_day: Decimal
    staff_name: str = Field(min_length=1, max_length=200)
    actual_service_days: int = Field(ge=0)
    rest_days: int = Field(ge=0)
    substitute_service_days: int = Field(ge=0)
    deferred_leave_days: int = Field(ge=0)
    leave_resolution_days: int = Field(ge=0)
    required_service_days: int = Field(ge=0)
    adjusted_assigned_start_date: date
    adjusted_assigned_end_date: date
    original_scheduled_service_days: int = Field(ge=0)
    makeup_service_days: int = Field(ge=0)


class CaseAssignmentSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_service_days: int = Field(ge=0)
    actual_service_days: int = Field(ge=0)
    actual_hours: Decimal
    adjusted_start_date: date
    adjusted_end_date: date
    target_service_days: int = Field(ge=0)
    target_service_hours: Decimal
    has_service_gap: bool
    has_service_overlap: bool
    rest_days: int = Field(ge=0)
    substitute_service_days: int = Field(ge=0)
    deferred_leave_days: int = Field(ge=0)


class CaseAssignmentListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignments: list[CaseAssignmentView]
    summary: CaseAssignmentSummaryView | None = None


__all__ = [
    "AssignmentScheduleAssignmentView",
    "AssignmentScheduleDayView",
    "AssignmentScheduleGuardView",
    "AssignmentScheduleView",
    "CaseAssignmentListView",
    "CaseAssignmentSummaryView",
    "CaseAssignmentView",
]

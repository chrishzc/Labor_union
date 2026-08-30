"""Closed Scheduling projection for the staff monthly calendar endpoint."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MonthlyScheduleDayView(_ClosedModel):
    work_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: Literal[
        "available",
        "working",
        "resting",
        "historical_assignment",
        "waiting_deposit_lock",
        "staff_unavailability",
    ]
    assignment_id: int | None = Field(default=None, gt=0)
    case_no: str | None = None
    staff_id: int = Field(gt=0)
    client_name: str | None = None
    order_status: str | None = None
    staff_name: str | None = None
    is_work_day: bool
    is_double_pay: bool
    notes: str | None = None
    lock_id: int | None = Field(default=None, gt=0)
    plan_id: int | None = Field(default=None, gt=0)
    unavailability_block_id: int | None = Field(default=None, gt=0)
    unavailability_kind: Literal["long_leave", "paused_service"] | None = None
    unavailability_reason: str | None = None


class MonthlyScheduleSummaryView(_ClosedModel):
    status: Literal["white", "yellow", "red", "green", "historical", "unavailable"]
    case_no: str | None = None
    client_name: str | None = None
    is_work_day: bool
    is_double_pay: bool
    assignment_id: int | None = Field(default=None, gt=0)
    lock_id: int | None = Field(default=None, gt=0)
    plan_id: int | None = Field(default=None, gt=0)
    unavailability_block_id: int | None = Field(default=None, gt=0)
    unavailability_kind: Literal["long_leave", "paused_service"] | None = None
    unavailability_reason: str | None = None


class StaffMonthlyScheduleView(_ClosedModel):
    staff_id: int = Field(gt=0)
    year: int = Field(ge=1900, le=2100)
    month: int = Field(ge=1, le=12)
    days: list[MonthlyScheduleDayView] = Field(min_length=28)
    schedule_map: dict[int, MonthlyScheduleSummaryView]


__all__ = ["StaffMonthlyScheduleView"]

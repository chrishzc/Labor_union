"""
File: scheduling_current.py
Description: 定義目前排班、檔期鎖與不可服務原因的 strict HTTP view。
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from domains.scheduling.current_projection import (
    AssignmentLifecycleStatus,
    SchedulingOccupancyKind,
)


class SchedulingCurrentAssignmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: int = Field(gt=0)
    case_no: str | None = None
    generation_id: int = Field(gt=0)
    scheduling_version: int = Field(ge=0)
    staff_id: int = Field(gt=0)
    status: AssignmentLifecycleStatus
    assigned_start_date: date
    assigned_end_date: date
    first_service_at: datetime
    completion_at: datetime
    official_service_day_count: int = Field(gt=0)
    actual_hours: int = Field(gt=0)


class SchedulingCurrentDayEntryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occupancy_kind: SchedulingOccupancyKind
    case_no: str | None = None
    assignment_id: int | None = Field(default=None, gt=0)
    assignment_status: AssignmentLifecycleStatus | None = None
    lock_id: int | None = Field(default=None, gt=0)
    segment_id: int | None = Field(default=None, gt=0)
    availability_block_id: int | None = Field(default=None, gt=0)
    unavailability_kind: str | None = None
    unavailability_reason: str | None = Field(default=None, min_length=1, max_length=500)


class SchedulingCurrentDayView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calendar_date: date
    available: bool
    entries: list[SchedulingCurrentDayEntryView]


class SchedulingCaseVersionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    scheduling_version: int = Field(ge=0)


class SchedulingCurrentProjectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    range_start: date
    range_end: date
    evaluated_at: datetime
    assignments: list[SchedulingCurrentAssignmentView]
    days: list[SchedulingCurrentDayView]
    case_versions: list[SchedulingCaseVersionView]
    projection_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class SchedulingCurrentTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, object]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "SchedulingCaseVersionView",
    "SchedulingCurrentAssignmentView",
    "SchedulingCurrentDayEntryView",
    "SchedulingCurrentDayView",
    "SchedulingCurrentProjectionView",
    "SchedulingCurrentTypedErrorView",
]

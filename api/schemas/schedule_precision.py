"""Closed transport projection for Scheduling attendance precision queries."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScheduleHolidayView(_ClosedModel):
    date: date
    name: str | None
    is_worked: bool


class ScheduleWeekView(_ClosedModel):
    week_num: int = Field(gt=0)
    start_date: date
    end_date: date
    work_days: int = Field(ge=0)
    rest_days: int = Field(ge=0)
    holiday_days: int = Field(ge=0)


class ScheduleDayView(_ClosedModel):
    date: date
    day_num: int = Field(gt=0)
    is_work_day: bool
    is_rest_day: bool
    holiday_name: str | None


class SchedulePrecisionResultView(_ClosedModel):
    actual_start_date: date
    actual_end_date: date
    target_service_days: int = Field(gt=0)
    total_calendar_days: int = Field(gt=0)
    actual_work_days_count: int = Field(ge=0)
    rest_days_count: int = Field(ge=0)
    national_holidays_found: list[ScheduleHolidayView]
    total_estimated_salary: float | None = Field(default=None, ge=0)
    weekly_stats: list[ScheduleWeekView]
    day_by_day: list[ScheduleDayView]


__all__ = ["SchedulePrecisionResultView"]

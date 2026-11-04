"""Strict transport schema for the read-only staff performance report."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PerformanceTotalsView(_Strict):
    case_count: int | None = Field(ge=0)
    service_hours: float | None = Field(ge=0)
    total_amount_ntd: int | None = Field(ge=0)


class PerformanceStaffView(_Strict):
    staff_id: int = Field(gt=0)
    union_no: str | None
    staff_name: str


class PerformanceTrendView(_Strict):
    start_date: date
    end_date: date
    label: str
    totals: PerformanceTotalsView


class PerformanceCaseView(_Strict):
    case_no: str
    service_start: date | None
    service_end: date | None
    work_days: int = Field(ge=0)
    service_hours: float | None = Field(ge=0)
    total_amount_ntd: int | None = Field(ge=0)
    actual_start_date: date | None
    primary_staff_id: int = Field(gt=0)
    recognized_case_count: int | None = Field(ge=0, le=1)
    recognized_amount_ntd: int | None = Field(ge=0)


class StaffPerformanceRowView(PerformanceStaffView):
    totals: PerformanceTotalsView
    previous_totals: PerformanceTotalsView
    cases: tuple[PerformanceCaseView, ...]
    trend: tuple[PerformanceTrendView, ...]


class StaffPerformanceReportView(_Strict):
    schema_version: Literal["staff-performance.v2"]
    period: Literal["month", "quarter", "year"]
    year: int
    month: int | None
    quarter: int | None
    start_date: date
    end_date: date
    through_date: date
    previous_start_date: date
    previous_end_date: date
    generated_at: datetime
    selected_staff_id: int | None
    available_years: tuple[int, ...]
    staff_options: tuple[PerformanceStaffView, ...]
    service_staff_count: int = Field(ge=0)
    totals: PerformanceTotalsView
    rows: tuple[StaffPerformanceRowView, ...]
    trend: tuple[PerformanceTrendView, ...]

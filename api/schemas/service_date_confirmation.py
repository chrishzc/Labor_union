"""Typed views for confirmed planned service dates."""

from datetime import date
from pydantic import BaseModel, ConfigDict, Field


class ServiceWeekView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_number: int = Field(gt=0)
    period_start: date
    period_end: date
    service_dates: list[date]
    service_day_count: int = Field(gt=0)


class BoundServiceStaffView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_id: int = Field(gt=0)
    staff_name: str = Field(min_length=1)


class ServiceDateConfirmationQueryView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    contracted_service_days: int = Field(gt=0)
    suggested_dates: list[date]
    selectable_dates: list[date]
    current_version: int | None = None
    current_dates: list[date]
    bound_staff: list[BoundServiceStaffView]
    arrangement_pending: bool


class HistoricalArrangementSegmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_id: int = Field(gt=0)
    assigned_start_date: date
    assigned_end_date: date
    service_dates: list[date] = Field(min_length=1)


class HistoricalArrangementPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    confirmed_version: int = Field(gt=0)
    segments: list[HistoricalArrangementSegmentView]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalArrangementReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    scheduling_version: int = Field(ge=0)
    generation_number: int = Field(gt=0)
    assignment_ids: list[int]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ServiceDateConfirmationPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    current_version: int | None = None
    service_dates: list[date]
    weeks: list[ServiceWeekView]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ServiceDateConfirmationReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    confirmed_version: int = Field(gt=0)
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    service_dates: list[date]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

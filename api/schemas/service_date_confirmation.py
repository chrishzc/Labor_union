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

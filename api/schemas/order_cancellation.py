"""Typed HTTP views for Orders Cancellation Query, Preview, and Apply."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CancellationServiceDayView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_date: date
    staff_id: int = Field(gt=0)
    reason: str | None = None


class CancellationCaregiverOptionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    display_name: str = Field(min_length=1)


class OrderCancellationQueryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    lifecycle_status: str
    actual_start_date: date | None
    contracted_service_days: int = Field(gt=0)
    service_hours_per_day: int = Field(gt=0)
    service_started: bool
    service_data_locked: bool
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    confirmed_service_days: list[CancellationServiceDayView]
    caregiver_options: list[CancellationCaregiverOptionView]


class OrderCancellationPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cancellation_date: date
    actual_end_date: date | None
    confirmed_service_days: list[CancellationServiceDayView]
    official_service_day_count: int = Field(ge=0)
    official_service_hours: int = Field(ge=0)
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    scheduling: dict[str, Any]
    client_finance_impact: dict[str, Any]
    payroll_impact: dict[str, Any]
    lifecycle_impact: dict[str, Any]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class OrderCancellationReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    lifecycle_status: str
    actual_end_date: date | None
    official_service_day_count: int = Field(ge=0)
    official_service_hours: int = Field(ge=0)
    cancelled_assignment_ids: list[int]
    created_assignment_keys: list[str]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class OrderCancellationTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None

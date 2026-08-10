"""Typed HTTP contracts for Orders Terms Query, Preview, and Apply."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ServiceTimeTermsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_time: time | None
    end_time: time | None
    end_day_offset: int | None = Field(ge=0, le=1)


class OrderTermsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planned_start_date: date
    service_days: int = Field(gt=0)
    service_hours_per_day: int = Field(gt=0)
    floor_fee_ntd: int = Field(ge=0)
    service_time: ServiceTimeTermsView


class OrderTermsQueryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    service_data_locked: bool
    terms: OrderTermsView


class OrderTermsPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: OrderTermsView
    after: OrderTermsView
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


class OrderTermsReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    lifecycle_status: str
    service_data_lock_formed: bool
    cancelled_assignment_ids: list[int]
    created_assignment_keys: list[str]
    official_service_day_count: int = Field(ge=0)
    official_service_hours: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class OrderTermsTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None

"""Typed HTTP views for Actual Start Query, Preview, and Apply."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ActualStartQueryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    current_actual_start_date: date | None
    planned_start_date: date
    service_data_locked: bool
    order_version: int = Field(ge=0)
    scheduling_version: int | None = Field(default=None, ge=0)
    scheduling_generation: int | None = Field(default=None, ge=0)
    client_finance_version: int | None = Field(default=None, ge=0)
    payroll_version: int | None = Field(default=None, ge=0)
    has_formal_assignments: bool


class ActualStartDateOnlyPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["date_only"]
    case_no: str
    before_actual_start_date: date | None
    after_actual_start_date: date
    order_version: int = Field(ge=0)
    scheduling_version: int | None = Field(default=None, ge=0)
    scheduling_generation: int | None = Field(default=None, ge=0)
    client_finance_version: int | None = Field(default=None, ge=0)
    payroll_version: int | None = Field(default=None, ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ActualStartReschedulePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["reschedule"]
    before_actual_start_date: date | None
    after_actual_start_date: date
    actual_end_date: date
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    actual_start: dict[str, Any]
    scheduling: dict[str, Any]
    lifecycle_impact: dict[str, Any]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


ActualStartPreviewView = Annotated[
    ActualStartDateOnlyPreviewView | ActualStartReschedulePreviewView,
    Field(discriminator="operation"),
]


class ActualStartDateOnlyResultView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["date_only"]
    case_no: str
    actual_start_date: date
    order_version: int = Field(ge=0)
    scheduling_version: int | None = Field(default=None, ge=0)
    scheduling_generation: int | None = Field(default=None, ge=0)
    client_finance_version: int | None = Field(default=None, ge=0)
    payroll_version: int | None = Field(default=None, ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    changed: bool


class ActualStartRescheduleReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["reschedule"]
    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    lifecycle_status: str
    service_data_lock_formed: bool
    cancelled_assignment_ids: list[int]
    created_assignment_keys: list[str]
    official_service_day_count: int = Field(ge=0)
    official_service_hours: float = Field(ge=0, multiple_of=0.5)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


ActualStartReceiptView = Annotated[
    ActualStartDateOnlyResultView | ActualStartRescheduleReceiptView,
    Field(discriminator="operation"),
]


class ActualStartTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None

"""Typed HTTP views for Assignment Plan Query, Preview, and Apply."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssignmentPlanSegmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: int | None = Field(default=None, gt=0)
    candidate_key: str | None = None
    staff_id: int = Field(gt=0)
    sequence: int = Field(gt=0)
    assigned_start_date: date
    assigned_end_date: date
    official_service_dates: list[date]
    actual_hours: int | None = Field(default=None, ge=0)
    lineage_source_assignment_ids: list[int] = Field(default_factory=list)


class AssignmentPlanQueryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    contracted_service_days: int = Field(gt=0)
    service_hours_per_day: int = Field(gt=0)
    service_started: bool
    assignments: list[AssignmentPlanSegmentView]


class AssignmentPlanPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    cancelled_assignment_ids: list[int]
    assignments: list[AssignmentPlanSegmentView]
    buffers: list[dict[str, Any]]
    client_finance_impact: dict[str, Any]
    payroll_impact: dict[str, Any]
    orders_impact: dict[str, Any]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssignmentPlanReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    cancelled_assignment_ids: list[int]
    created_assignment_keys: list[str]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssignmentPlanTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None

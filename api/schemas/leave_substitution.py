"""Typed HTTP views for Scheduling leave/substitution Preview and Apply."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.assignment_plan import AssignmentPlanSegmentView


class LeaveSubstitutionOutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_index: int = Field(ge=0)
    original_schedule_id: int = Field(gt=0)
    original_assignment_id: int = Field(gt=0)
    original_staff_id: int = Field(gt=0)
    original_work_date: date
    resolution_type: str
    leave_occupancy_date: date
    resulting_service_date: date
    resulting_staff_id: int = Field(gt=0)
    resulting_assignment_key: str
    is_double_pay: bool


class LeaveSubstitutionPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    cancelled_assignment_ids: list[int]
    assignments: list[AssignmentPlanSegmentView]
    outcomes: list[LeaveSubstitutionOutcomeView]
    client_finance_impact: dict[str, Any]
    payroll_impact: dict[str, Any]
    orders_impact: dict[str, Any]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class LeaveSubstitutionReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_key: str
    case_no: str
    order_version: int = Field(ge=0)
    scheduling_generation: int = Field(ge=0)
    scheduling_version: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    outcome_event_ids: list[int]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class LeaveSubstitutionTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None

"""Typed HTTP views for controlled order reopening."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrderReopenPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    client_finance_version: int = Field(ge=0)
    payroll_version: int = Field(ge=0)
    cancellation_event_id: int = Field(gt=0)
    before_status: str
    after_status: str
    requires_fresh_scheduling_preview: bool
    restored_assignment_ids: list[int]
    restored_schedule_ids: list[int]
    restored_lock_ids: list[int]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class OrderReopenReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    order_version: int = Field(ge=0)
    lifecycle_status: str
    cancellation_event_id: int = Field(gt=0)
    requires_fresh_scheduling_preview: bool
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class OrderReopenTypedErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None

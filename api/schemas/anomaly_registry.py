"""Typed HTTP contracts for the Anomalies registry vertical."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ClaimAnomalyBody(_StrictModel):
    expected_workflow_version: int = Field(ge=0)


class ResolveAnomalyBody(_StrictModel):
    expected_workflow_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


class DomainActionView(_StrictModel):
    action_code: str
    owning_domain: str
    command_name: str
    requires_preview: bool


class StaffCalendarNavigationView(_StrictModel):
    staff_id: int = Field(gt=0)
    target_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class AnomalySummaryView(_StrictModel):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    definition_code: str
    source_domain: str
    source_identity: str
    source_version: int = Field(ge=0)
    severity: str
    predicate_active: bool
    workflow_status: str
    workflow_version: int = Field(ge=0)
    display_snapshot: dict[str, Any] | None = None
    staff_calendar_navigation: StaffCalendarNavigationView | None = None


class AnomalyDetailView(_StrictModel):
    summary: AnomalySummaryView
    timeline: list[dict[str, Any]]
    available_actions: list[DomainActionView]


class AnomalyWorkflowReceiptView(_StrictModel):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: str
    resulting_workflow_version: int = Field(ge=0)
    workflow_status: str


class AnomalyTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


__all__ = [
    "AnomalyDetailView",
    "AnomalySummaryView",
    "AnomalyTypedErrorView",
    "AnomalyWorkflowReceiptView",
    "ClaimAnomalyBody",
    "ResolveAnomalyBody",
]

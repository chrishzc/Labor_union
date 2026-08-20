"""
File: anomaly_registry.py
Description: 定義異常清單、詳情與人工流程的嚴格 HTTP 契約。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domains.anomalies.registry import AlertWorkflowStatus, AnomalySeverity


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ClaimAnomalyBody(_StrictModel):
    expected_workflow_version: int = Field(ge=0)


class ResolveAnomalyBody(_StrictModel):
    expected_workflow_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


class DomainActionView(_StrictModel):
    action_key: str
    label: str
    owning_domain: str
    form_schema_key: str
    source_binding_keys: list[str]
    source_bindings: dict[str, str | int] | None = None
    required_operator_inputs: list[str]
    preview_operation: str
    apply_operation: str | None = None
    required_capability: str | None = None
    completion_predicate: str
    action_contract_version: int = Field(ge=1)
    requires_preview: bool

    @property
    def action_code(self) -> str:
        return self.action_key

    @property
    def command_name(self) -> str:
        return self.preview_operation


class StaffCalendarNavigationView(_StrictModel):
    staff_id: int = Field(gt=0)
    target_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class AnomalySummaryView(_StrictModel):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    definition_code: str
    source_domain: str
    source_identity: str
    source_version: int = Field(ge=0)
    severity: AnomalySeverity
    predicate_active: bool
    workflow_status: AlertWorkflowStatus
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
    workflow_status: AlertWorkflowStatus


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

"""Typed HTTP views for Anomalies root-fact recovery."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RecoveryActionView(_StrictModel):
    action_key: str
    label: str
    owning_domain: str
    form_schema_key: str
    source_binding_keys: list[str]
    source_bindings: dict[str, str | int]
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


class FinanceOccurrenceView(_StrictModel):
    occurrence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    definition_code: str
    source_event_identity: str
    finance_import_row_id: int = Field(gt=0)
    finance_import_batch_id: int = Field(gt=0)
    source_version: int = Field(ge=0)
    occurred_at: str
    bounded_snapshot: dict[str, Any]


class AnomalyRecoveryContextView(_StrictModel):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    definition_code: str
    source_domain: str
    source_identity: str
    source_version: int = Field(ge=0)
    severity: str
    predicate_active: bool
    workflow_status: str
    workflow_version: int = Field(ge=0)
    domain_blocker_active: bool
    projection_freshness: str
    root_fact_snapshot: dict[str, Any]
    occurrence_timeline: list[FinanceOccurrenceView]
    workflow_timeline: list[dict[str, Any]]
    available_actions: list[RecoveryActionView]


class AnomalyRecoveryTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


class ScanAnomalyDefinitionBody(_StrictModel):
    maximum_items: int = Field(default=50, ge=1, le=100)
    after_source_id: int = Field(default=0, ge=0)


class ScanAnomalyDefinitionResultView(_StrictModel):
    definition_code: str
    scanned_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    inactive_count: int = Field(ge=0)
    next_after_source_id: int | None = Field(default=None, ge=1)
    completed: bool


class RetryAnomalyProjectorBody(_StrictModel):
    maximum_events: int = Field(default=50, ge=1, le=100)


class RetryAnomalyProjectorResultView(_StrictModel):
    projector_identity: str
    requeued_event_ids: list[int]
    requeued_count: int = Field(ge=0)


__all__ = [
    "AnomalyRecoveryContextView",
    "AnomalyRecoveryTypedErrorView",
    "FinanceOccurrenceView",
    "RecoveryActionView",
    "RetryAnomalyProjectorBody",
    "RetryAnomalyProjectorResultView",
    "ScanAnomalyDefinitionBody",
    "ScanAnomalyDefinitionResultView",
]

"""
File: anomaly_recovery.py
Description: 定義異常根事實修復查詢與維運操作的嚴格 HTTP 契約。
"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from api.schemas.anomaly_registry import (
    AnomalyDisplaySnapshotView,
    AnomalySourceBindingView,
    AnomalyTimelineEventView,
)
from domains.anomalies.registry import AlertWorkflowStatus, AnomalySeverity


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RecoveryActionView(_StrictModel):
    action_key: str
    label: str
    owning_domain: str
    form_schema_key: str
    source_binding_keys: list[str]
    source_bindings: list[AnomalySourceBindingView]
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
    bounded_snapshot: "AnomalyDisplaySnapshotView"


class AnomalyRootFactSnapshotView(_StrictModel):
    """Root fact 的安全標量與計數投影，不包含原始 identity 或 payload。"""

    occurred_at: datetime
    source_version: int = Field(ge=0)
    finance_import_row_identity: str = Field(min_length=1, max_length=191)
    finance_import_batch_identity: str = Field(min_length=1, max_length=191)
    original_refund_ledger_entry_identity: str | None = Field(
        default=None,
        min_length=1,
        max_length=191,
    )
    amount_delta_ntd: int
    root_condition_active: bool
    integrity_blocker_active: bool
    affected_order_identities: list[str] = Field(default_factory=list, max_length=100)
    affected_obligation_identities: list[str] = Field(default_factory=list, max_length=100)
    domain_blockers: list[str] = Field(default_factory=list, max_length=20)
    reason_codes: list[str] = Field(default_factory=list, max_length=20)


class AnomalyRecoveryContextView(_StrictModel):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    definition_code: str
    source_domain: str
    source_identity: str
    source_version: int = Field(ge=0)
    severity: AnomalySeverity
    predicate_active: bool
    workflow_status: AlertWorkflowStatus
    workflow_version: int = Field(ge=0)
    domain_blocker_active: bool
    projection_freshness: str
    root_fact_snapshot: AnomalyRootFactSnapshotView
    occurrence_timeline: list[FinanceOccurrenceView]
    workflow_timeline: list[AnomalyTimelineEventView]
    available_actions: list[RecoveryActionView]


class AnomalyRecoveryTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    correlation_id: str
    field_errors: list["AnomalyRecoveryFieldErrorView"] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


class AnomalyRecoveryFieldErrorView(_StrictModel):
    field: str = Field(min_length=1, max_length=191)
    code: str = Field(min_length=1, max_length=191)
    message: str = Field(min_length=1, max_length=500)


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


class ProjectorDeadLetterView(_StrictModel):
    projector_identity: str = Field(min_length=1, max_length=100)
    event_id: int = Field(gt=0)
    intent_type: str = Field(min_length=1, max_length=191)
    attempt_count: int = Field(ge=3)
    error_code: str = Field(min_length=1, max_length=191)
    failed_at: datetime
    available_actions: list[str]
    successor_event_id: int | None = Field(default=None, gt=0)
    successor_source_version: int | None = Field(default=None, gt=0)


class RetryProjectorDeadLetterPreviewBody(_StrictModel):
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str = Field(min_length=1, max_length=500)


class RetryProjectorDeadLetterPreviewView(_StrictModel):
    projector_identity: str
    event_id: int = Field(gt=0)
    intent_type: str
    expected_attempt_count: int = Field(ge=3)
    error_code: str
    reason: str
    evidence_reference: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class RetryProjectorDeadLetterApplyBody(RetryProjectorDeadLetterPreviewBody):
    expected_attempt_count: int = Field(ge=3)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class RetryProjectorDeadLetterReceiptView(_StrictModel):
    projector_identity: str
    event_id: int = Field(gt=0)
    prior_attempt_count: int = Field(ge=3)
    resulting_status: str
    receipt_identity: str
    replayed: bool


class SupersedeProjectorDeadLetterPreviewView(_StrictModel):
    projector_identity: str
    event_id: int = Field(gt=0)
    intent_type: str
    expected_attempt_count: int = Field(ge=3)
    successor_event_id: int = Field(gt=0)
    successor_source_version: int = Field(gt=0)
    successor_predicate_active: bool
    reason: str
    evidence_reference: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class SupersedeProjectorDeadLetterApplyBody(
    RetryProjectorDeadLetterPreviewBody
):
    expected_attempt_count: int = Field(ge=3)
    expected_successor_event_id: int = Field(gt=0)
    expected_successor_source_version: int = Field(gt=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class SupersedeProjectorDeadLetterReceiptView(_StrictModel):
    projector_identity: str
    event_id: int = Field(gt=0)
    successor_event_id: int = Field(gt=0)
    successor_source_version: int = Field(gt=0)
    resulting_status: str
    receipt_identity: str
    replayed: bool


__all__ = [
    "AnomalyRecoveryContextView",
    "AnomalyRecoveryFieldErrorView",
    "AnomalyRootFactSnapshotView",
    "AnomalyRecoveryTypedErrorView",
    "FinanceOccurrenceView",
    "RecoveryActionView",
    "ProjectorDeadLetterView",
    "RetryAnomalyProjectorBody",
    "RetryAnomalyProjectorResultView",
    "RetryProjectorDeadLetterApplyBody",
    "RetryProjectorDeadLetterPreviewBody",
    "RetryProjectorDeadLetterPreviewView",
    "RetryProjectorDeadLetterReceiptView",
    "SupersedeProjectorDeadLetterApplyBody",
    "SupersedeProjectorDeadLetterPreviewView",
    "SupersedeProjectorDeadLetterReceiptView",
    "ScanAnomalyDefinitionBody",
    "ScanAnomalyDefinitionResultView",
]

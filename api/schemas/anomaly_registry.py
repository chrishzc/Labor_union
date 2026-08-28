"""
File: anomaly_registry.py
Description: 定義異常清單、詳情與人工流程的嚴格 HTTP 契約。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from domains.anomalies.registry import AlertWorkflowStatus, AnomalySeverity


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ClaimAnomalyBody(_StrictModel):
    expected_workflow_version: int = Field(ge=0)


class ResolveAnomalyBody(_StrictModel):
    expected_workflow_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


class _AnomalyEvidenceBase(_StrictModel):
    key: str = Field(min_length=1, max_length=191, pattern=r"^[A-Za-z0-9_.:-]+$")


class AnomalyIdentityEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["identity"]
    value: str = Field(min_length=1, max_length=191)


class AnomalyMaskedTextEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["masked_text"]
    value: str = Field(min_length=1, max_length=191)


class AnomalyDateEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["date"]
    value: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class AnomalyDatetimeEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["datetime"]
    value: datetime


class AnomalyBooleanEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["boolean"]
    value: bool


class AnomalyMoneyEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["money_ntd"]
    value: int


class AnomalyIntegerEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["integer"]
    value: int


class AnomalyCodeEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["code"]
    value: str = Field(min_length=1, max_length=191)


class AnomalyCodeListEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["code_list"]
    value: list[str] = Field(max_length=100)


class AnomalyIdentityListEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["identity_list"]
    value: list[str] = Field(max_length=100)


class AnomalyDetailListEvidenceView(_AnomalyEvidenceBase):
    kind: Literal["detail_list"]
    value: list[str] = Field(max_length=100)


AnomalyEvidenceFieldView = Annotated[
    AnomalyIdentityEvidenceView
    | AnomalyMaskedTextEvidenceView
    | AnomalyDateEvidenceView
    | AnomalyDatetimeEvidenceView
    | AnomalyBooleanEvidenceView
    | AnomalyMoneyEvidenceView
    | AnomalyIntegerEvidenceView
    | AnomalyCodeEvidenceView
    | AnomalyCodeListEvidenceView
    | AnomalyIdentityListEvidenceView
    | AnomalyDetailListEvidenceView,
    Field(discriminator="kind"),
]


class AnomalyDisplaySnapshotView(_StrictModel):
    """Definition-specific 顯示摘要的固定遮罩投影。"""

    redaction_version: Literal["anomaly-safe.v1"]
    definition_code: str = Field(min_length=1, max_length=191)
    fields: list[AnomalyEvidenceFieldView] = Field(default_factory=list, max_length=20)


class _AnomalySourceBindingBase(_StrictModel):
    key: str = Field(min_length=1, max_length=191, pattern=r"^[A-Za-z0-9_.:-]+$")


class AnomalyIdentityBindingView(_AnomalySourceBindingBase):
    kind: Literal["identity"]
    value: str = Field(min_length=1, max_length=191)


class AnomalyVersionBindingView(_AnomalySourceBindingBase):
    kind: Literal["version"]
    value: int = Field(ge=0)


AnomalySourceBindingView = Annotated[
    AnomalyIdentityBindingView | AnomalyVersionBindingView,
    Field(discriminator="kind"),
]


class DomainActionView(_StrictModel):
    action_key: str
    label: str
    owning_domain: str
    form_schema_key: str
    source_binding_keys: list[str]
    source_bindings: list[AnomalySourceBindingView] | None = None
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
    display_snapshot: AnomalyDisplaySnapshotView | None = None
    staff_calendar_navigation: StaffCalendarNavigationView | None = None


class AnomalyTimelineEventView(_StrictModel):
    action: Literal["claim", "resolve", "reopen", "auto_resolve"]
    expected_workflow_version: int = Field(ge=0)
    resulting_workflow_version: int = Field(ge=0)
    actor: str = Field(min_length=1, max_length=191)
    reason: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)
    created_at: datetime


class AnomalyDetailView(_StrictModel):
    summary: AnomalySummaryView
    timeline: list[AnomalyTimelineEventView]
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
    field_errors: list["AnomalyFieldErrorView"] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    current_version: int | None = None


class AnomalyFieldErrorView(_StrictModel):
    field: str = Field(min_length=1, max_length=191)
    code: str = Field(min_length=1, max_length=191)
    message: str = Field(min_length=1, max_length=500)


__all__ = [
    "AnomalyBooleanEvidenceView",
    "AnomalyCodeEvidenceView",
    "AnomalyCodeListEvidenceView",
    "AnomalyDateEvidenceView",
    "AnomalyDatetimeEvidenceView",
    "AnomalyDetailListEvidenceView",
    "AnomalyDetailView",
    "AnomalyDisplaySnapshotView",
    "AnomalyEvidenceFieldView",
    "AnomalyFieldErrorView",
    "AnomalyIdentityBindingView",
    "AnomalyIdentityEvidenceView",
    "AnomalyIdentityListEvidenceView",
    "AnomalyIntegerEvidenceView",
    "AnomalyMaskedTextEvidenceView",
    "AnomalyMoneyEvidenceView",
    "AnomalySourceBindingView",
    "AnomalySummaryView",
    "AnomalyTimelineEventView",
    "AnomalyTypedErrorView",
    "AnomalyVersionBindingView",
    "AnomalyWorkflowReceiptView",
    "ClaimAnomalyBody",
    "ResolveAnomalyBody",
]

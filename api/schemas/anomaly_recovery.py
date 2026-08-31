"""
File: anomaly_recovery.py
Description: 定義異常根事實修復查詢與維運操作的嚴格 HTTP 契約。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.anomaly_registry import (
    AnomalyDisplaySnapshotView,
    AnomalySourceBindingView,
)
from domains.anomalies.registry import AnomalySeverity


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


class AnomalyRecoveryContextView(_StrictModel):
    """Generic recovery context shared by current and compatibility callers."""

    issue_key: str = Field(pattern=r"^ci_[0-9a-f]{64}$")
    definition_code: str
    owner_domain: str
    owner_root_type: str
    subject: AnomalyDisplaySnapshotView
    owner_snapshot_token: str = Field(min_length=1, max_length=191)
    owner_version: int = Field(ge=0)
    severity: AnomalySeverity
    blocking: bool
    details_version: int = Field(ge=1)
    details: AnomalyDisplaySnapshotView
    episode_started_at: datetime
    last_verified_at: datetime
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


class CurrentAnomalyRecoveryContextView(AnomalyRecoveryContextView):
    """Closed current public recovery payload for the LINE-006 registry."""

    definition_code: Literal["LINE-006"]


__all__ = [
    "AnomalyRecoveryContextView",
    "CurrentAnomalyRecoveryContextView",
    "AnomalyRecoveryFieldErrorView",
    "AnomalyRecoveryTypedErrorView",
    "RecoveryActionView",
]

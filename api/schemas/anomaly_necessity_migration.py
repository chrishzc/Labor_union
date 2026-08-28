"""
File: anomaly_necessity_migration.py
Description: 定義只供核准 runner 使用的異常必要性移轉 HTTP 契約。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from domains.anomalies.maintenance import AnomalyReclassificationDisposition


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class AnomalyNecessityMigrationCursorView(_StrictModel):
    definition_code: str = Field(min_length=1, max_length=191)
    source_identity: str = Field(min_length=1, max_length=191)


class AnomalyNecessityMigrationAlertView(_StrictModel):
    alert_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    definition_code: str = Field(min_length=1, max_length=191)
    source_identity: str = Field(min_length=1, max_length=191)
    source_version: StrictInt = Field(ge=0)
    workflow_version: StrictInt = Field(ge=0)


class AnomalyNecessityMigrationPageView(_StrictModel):
    items: list[AnomalyNecessityMigrationAlertView]
    next_cursor: AnomalyNecessityMigrationCursorView | None
    policy_identity: str = Field(min_length=1, max_length=191)
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AnomalyNecessityMigrationIntentBody(_StrictModel):
    expected_definition_code: str = Field(min_length=1, max_length=191)
    expected_source_identity: str = Field(min_length=1, max_length=191)
    expected_source_version: StrictInt = Field(ge=0)
    expected_workflow_version: StrictInt = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str = Field(min_length=1, max_length=500)


class AnomalyNecessityMigrationApplyBody(
    AnomalyNecessityMigrationIntentBody
):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AnomalyNecessityMigrationTargetView(_StrictModel):
    target_domain: str = Field(min_length=1, max_length=191)
    target_reference: str = Field(min_length=1, max_length=191)
    target_version: StrictInt = Field(ge=0)


class AnomalyNecessityMigrationPreviewView(_StrictModel):
    disposition_identity: str = Field(min_length=1, max_length=191)
    disposition: AnomalyReclassificationDisposition
    alert: AnomalyNecessityMigrationAlertView
    target: AnomalyNecessityMigrationTargetView | None
    rulebook_reference: str = Field(min_length=1, max_length=500)
    release_evidence_reference: str = Field(min_length=1, max_length=500)
    policy_identity: str = Field(min_length=1, max_length=191)
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AnomalyNecessityMigrationReceiptView(_StrictModel):
    disposition_identity: str = Field(min_length=1, max_length=191)
    receipt_identity: str = Field(min_length=1, max_length=191)
    disposition: AnomalyReclassificationDisposition
    alert: AnomalyNecessityMigrationAlertView
    policy_identity: str = Field(min_length=1, max_length=191)
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)
    created_at: datetime
    workflow_event_id: StrictInt = Field(gt=0)
    resulting_workflow_version: StrictInt = Field(gt=0)
    before_state_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    after_state_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    resulting_predicate_active: bool
    replayed: bool


class AnomalyNecessityMigrationTypedErrorView(_StrictModel):
    category: str
    code: str
    message: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    correlation_id: str
    current_version: StrictInt | None = None


class AnomalyNecessityMigrationErrorDetailView(_StrictModel):
    error: AnomalyNecessityMigrationTypedErrorView


class AnomalyNecessityMigrationErrorEnvelopeView(_StrictModel):
    detail: AnomalyNecessityMigrationErrorDetailView


__all__ = [
    "AnomalyNecessityMigrationAlertView",
    "AnomalyNecessityMigrationApplyBody",
    "AnomalyNecessityMigrationCursorView",
    "AnomalyNecessityMigrationErrorEnvelopeView",
    "AnomalyNecessityMigrationIntentBody",
    "AnomalyNecessityMigrationPageView",
    "AnomalyNecessityMigrationPreviewView",
    "AnomalyNecessityMigrationReceiptView",
    "AnomalyNecessityMigrationTargetView",
    "AnomalyNecessityMigrationTypedErrorView",
]

"""
File: runtime_health.py
Description: 定義 runtime health 與 LINE alert target 的封閉 HTTP schema。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RuntimeHealthRecordResponse(BaseModel):
    check_name: str
    component: str
    status: str
    raw_status: str
    message: str
    response_ms: int | None
    consecutive_failures: int
    consecutive_successes: int
    checked_at: datetime
    status_changed_at: datetime


class RuntimeHealthEventResponse(BaseModel):
    event_id: int
    check_name: str
    component: str
    transition_type: str
    before_status: str | None
    resulting_status: str
    message: str
    occurred_at: datetime


class AlertAdminTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    admin_user_id: int = Field(gt=0)
    minimum_status: str = Field(pattern="^(warning|critical)$")
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class AlertAdminTargetApplyRequest(AlertAdminTargetRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ResetLineAlertGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    expected_version: str = Field(min_length=1, max_length=191)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class ResetLineAlertGroupApplyRequest(ResetLineAlertGroupRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AlertTargetEnabledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    expected_version: str = Field(min_length=1, max_length=191)
    enabled: bool
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class AlertTargetEnabledApplyRequest(AlertTargetEnabledRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AlertTargetViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    target_id: int = Field(gt=0)
    target_kind: Literal["group", "admin_user"]
    display_label: str
    state: Literal["active", "disabled"]
    minimum_status: Literal["warning", "critical"]
    current_version: str
    updated_at: datetime


class AlertAdminCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    candidate_id: int = Field(gt=0)
    display_label: str
    line_linked: bool


class SafeReviewLinkIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    link_id: str = Field(min_length=1, max_length=191)
    raw_token: str = Field(min_length=16, max_length=512)
    canonical_internal_target: str = Field(min_length=1, max_length=191)
    target_version: int = Field(ge=0)
    source_alert_identity: str = Field(min_length=1, max_length=191)
    allowed_actor_ref: str = Field(min_length=1, max_length=191)
    required_capability: str = Field(min_length=1, max_length=100)
    ttl_seconds: int = Field(ge=1, le=900)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class SafeReviewLinkRedeemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    raw_token: str = Field(min_length=1, max_length=512)
    capability: str = Field(min_length=1, max_length=100)
    current_target: str = Field(min_length=1, max_length=191)
    current_target_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class SafeReviewLinkRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class SafeReviewLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    link_id: str
    status: Literal["issued", "redeemed", "expired", "revoked"]
    canonical_internal_target: str
    target_version: int = Field(ge=0)
    source_alert_identity: str
    expires_at_utc: datetime
    redeemed_at_utc: datetime | None
    revoked_at_utc: datetime | None
    root_version: int = Field(ge=0)


class SafeReviewLinkReceiptResponse(BaseModel):
    receipt_id: str
    outcome: Literal["issued", "redeemed", "expired", "revoked"]
    replayed: bool
    root_version: int = Field(ge=0)
    readback: SafeReviewLinkResponse


class AlertTargetMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    receipt_id: str
    command_family: Literal["line_alert_target"]
    operation: Literal["group_reset", "enable", "disable", "admin_target_add"]
    target_id: int = Field(gt=0)
    previous_state: Literal["active", "disabled"]
    resulting_state: Literal["active", "disabled"]
    current_version: str
    replayed: bool
    correlation_id: str
    committed_at: datetime


class AlertTargetMutationPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    operation: Literal["group_reset", "enable", "disable", "admin_target_add"]
    target_id: int | None = Field(default=None, gt=0)
    previous_state: Literal["absent", "active", "disabled"]
    resulting_state: Literal["active", "disabled"]
    current_version: str
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    apply_ready: Literal[True]


class _ClosedProbeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ApiHealthView(_ClosedProbeModel):
    status: Literal["healthy"]
    service: Literal["Labor Union API"]


class PrivateRuntimeCheckView(_ClosedProbeModel):
    status: Literal["ready"]
    service: str = Field(min_length=1, max_length=100)

"""
File: line_identity.py
Description: 定義 canonical LINE LIFF、登記與管理端身分流程的 public schemas。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LiffIdentityContext(BaseModel):
    flow_id: str = Field(min_length=1, max_length=191)
    line_id_token: str = Field(default="", max_length=4096)
    development_line_user_id: str = Field(default="", max_length=191)


class LineIdentityFlowValidationRequest(LiffIdentityContext):
    purpose: Literal["customer_binding", "staff_verification", "admin_binding", "staff_self_service"]


class LineIdentityFlowOpenRequest(BaseModel):
    purpose: Literal["customer_binding", "staff_verification", "admin_binding", "staff_self_service"]
    idempotency_key: str = Field(min_length=1, max_length=191)
    line_id_token: str = Field(default="", max_length=4096)
    development_line_user_id: str = Field(default="", max_length=191)


class LineIdentityFlowOpenResponse(BaseModel):
    flow_id: str
    purpose: str
    expires_at: datetime


class LineIdentityFlowValidationResponse(BaseModel):
    status: Literal["active"]
    expires_at: datetime


class CustomerIdentityRequest(LiffIdentityContext):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=30)


class CustomerIdentityApplyRequest(CustomerIdentityRequest):
    expected_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffIdentityRequest(LiffIdentityContext):
    name: str = Field(min_length=1, max_length=100)
    identity_card: str = Field(min_length=1, max_length=20)
    birthday: date


class StaffIdentityApplyRequest(StaffIdentityRequest):
    expected_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class AdminIdentityBindingRequest(LiffIdentityContext):
    username: str = Field(min_length=1, max_length=100)
    password: SecretStr


class AdminIdentityBindingApplyRequest(AdminIdentityBindingRequest):
    expected_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class LineIdentityCandidateResponse(BaseModel):
    currently_bound: bool


class LineIdentityPreviewResponse(BaseModel):
    status: str
    expected_version: int
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate: LineIdentityCandidateResponse | None = None


class LineIdentityApplyResponse(BaseModel):
    status: str
    review_request_id: int | None = None
    receipt_identity: str = Field(min_length=1, max_length=255)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProvisionalRegistrationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str | None = Field(default=None, max_length=191)
    line_id_token: str = Field(default="", max_length=4096)
    development_line_user_id: str = Field(default="", max_length=191)
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=30)
    expected_date: str = Field(min_length=1, max_length=100)
    service_days: int = Field(gt=0)
    address: str = Field(min_length=1, max_length=255)
    gender: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    birth_date: str | None = Field(default=None, max_length=50)
    tel: str | None = Field(default=None, max_length=50)
    ext: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=100)
    zip_code: str | None = Field(default=None, max_length=20)
    id_number: str | None = Field(default=None, max_length=50)
    liff_config_revision: str | None = Field(default=None, max_length=191)
    survey_details: dict[str, Any] = Field(default_factory=dict)


class ProvisionalRegistrationRequest(ProvisionalRegistrationPreviewRequest):
    expected_binding_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProvisionalRegistrationPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    expected_binding_version: int
    payload_fingerprint: str
    preview_fingerprint: str


class ProvisionalRegistrationResponse(BaseModel):
    registration_id: int
    client_id: int
    beclass_record_id: int
    client_name: str
    replayed: bool
    identity_status: str | None = None


class LineIdentityRuntimeConfigResponse(BaseModel):
    liff_id: str
    public_base_url: str | None = None


class CanonicalLineReviewDecisionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class CanonicalLineReviewDecisionRequest(CanonicalLineReviewDecisionPreviewRequest):
    idempotency_key: str = Field(min_length=1, max_length=191)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class CanonicalLineReviewDecisionPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: int
    decision: str
    before_status: str
    after_status: str
    expected_version: int
    resulting_version: int
    subject_type: str | None
    subject_reference: str | None
    line_user_id: str
    preview_fingerprint: str


class CanonicalLineReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: int
    review_type: str
    status: str
    version: int
    subject_type: str | None
    subject_reference: str | None
    assigned_admin_id: int | None
    due_at: datetime | None
    line_user_id: str
    display_name: str
    decision_reason: str | None
    reviewed_by_actor_id: str | None
    reviewed_at: datetime | None
    created_at: datetime | None
    outcome: str | None = None
    receipt_identity: str | None = None


class CanonicalLineReviewPageResponse(BaseModel):
    items: list[CanonicalLineReviewResponse]
    next_cursor: str | None


class CanonicalLineReviewNumberedPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[CanonicalLineReviewResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class CanonicalLineReviewSummaryResponse(BaseModel):
    pending_total: int
    staff_pending: int
    rebind_pending: int
    processed_today: int
    stale_pending: int
    stale_hours: int

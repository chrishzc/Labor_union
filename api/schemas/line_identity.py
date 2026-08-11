"""Public LIFF and administrator schemas for canonical LINE identity workflows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, SecretStr


class LiffIdentityContext(BaseModel):
    flow_id: str = Field(min_length=1, max_length=191)
    line_id_token: str = Field(default="", max_length=4096)
    development_line_user_id: str = Field(default="", max_length=191)


class CustomerIdentityRequest(LiffIdentityContext):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=30)


class StaffIdentityRequest(LiffIdentityContext):
    name: str = Field(min_length=1, max_length=100)
    identity_card: str = Field(min_length=1, max_length=20)
    birthday: date


class AdminIdentityBindingRequest(LiffIdentityContext):
    username: str = Field(min_length=1, max_length=100)
    password: SecretStr


class LineIdentityCandidateResponse(BaseModel):
    currently_bound: bool


class LineIdentityPreviewResponse(BaseModel):
    status: str
    expected_version: int
    candidate: LineIdentityCandidateResponse | None = None


class LineIdentityApplyResponse(BaseModel):
    status: str
    review_request_id: int | None = None


class ProvisionalRegistrationRequest(BaseModel):
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


class ProvisionalRegistrationResponse(BaseModel):
    registration_id: int
    client_id: int
    beclass_record_id: int
    client_name: str
    replayed: bool


class LineIdentityRuntimeConfigResponse(BaseModel):
    liff_id: str


class CanonicalLineReviewDecisionRequest(BaseModel):
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=191)
    reason: str = Field(min_length=1, max_length=1000)


class CanonicalLineReviewResponse(BaseModel):
    request_id: int
    review_type: str
    status: str
    version: int
    subject_type: str | None
    subject_reference: str | None
    assigned_admin_id: int | None
    due_at: datetime | None
    line_user_id_masked: str
    display_name: str
    decision_reason: str | None
    reviewed_by_actor_id: str | None
    reviewed_at: datetime | None
    created_at: datetime | None


class CanonicalLineReviewPageResponse(BaseModel):
    items: list[CanonicalLineReviewResponse]
    next_cursor: str | None


class CanonicalLineReviewSummaryResponse(BaseModel):
    pending_total: int
    staff_pending: int
    rebind_pending: int
    processed_today: int
    stale_pending: int
    stale_hours: int

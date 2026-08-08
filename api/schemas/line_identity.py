"""Public LIFF and administrator schemas for canonical LINE identity workflows."""

from __future__ import annotations

from datetime import date, datetime

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

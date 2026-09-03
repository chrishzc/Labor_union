"""
File: line_identity.py
Description: 定義 canonical LINE LIFF、登記與管理端身分流程的 public schemas。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


_TAIWAN_ID_LETTER_CODES = {
    "A": 10,
    "B": 11,
    "C": 12,
    "D": 13,
    "E": 14,
    "F": 15,
    "G": 16,
    "H": 17,
    "I": 34,
    "J": 18,
    "K": 19,
    "L": 20,
    "M": 21,
    "N": 22,
    "O": 35,
    "P": 23,
    "Q": 24,
    "R": 25,
    "S": 26,
    "T": 27,
    "U": 28,
    "V": 29,
    "W": 32,
    "X": 30,
    "Y": 31,
    "Z": 33,
}


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

    @field_validator("id_number")
    @classmethod
    def validate_id_number(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value
        candidate = value.strip()
        if not re.fullmatch(r"[A-Z][12]\d{8}", candidate):
            raise ValueError("id_number must be a valid Taiwan national ID number")
        letter_code = _TAIWAN_ID_LETTER_CODES[candidate[0]]
        digits = [int(char) for char in candidate[1:]]
        checksum = (
            letter_code // 10
            + (letter_code % 10) * 9
            + sum(digit * weight for digit, weight in zip(digits, (8, 7, 6, 5, 4, 3, 2, 1, 1)))
        )
        if checksum % 10 != 0:
            raise ValueError("id_number must be a valid Taiwan national ID number")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()):
            raise ValueError("email must be a valid email address")
        return value

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value
        candidate = value.strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
            raise ValueError("birth_date must be a valid YYYY-MM-DD date")
        try:
            parsed = date.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError("birth_date must be a valid YYYY-MM-DD date") from exc
        if parsed > date.today():
            raise ValueError("birth_date cannot be later than today")
        return value

    @field_validator("expected_date")
    @classmethod
    def validate_expected_date(cls, value: str) -> str:
        candidate = value.strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
            raise ValueError("expected_date must be a valid YYYY-MM-DD date")
        try:
            date.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError("expected_date must be a valid YYYY-MM-DD date") from exc
        return value


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

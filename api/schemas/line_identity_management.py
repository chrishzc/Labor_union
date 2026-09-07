"""Typed API views for administrative LINE identity management."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from subsystems.line.identity_management_contracts import (
    LineIdentityCurrentFactFinding,
    LineIdentityCurrentFactReadbackStatus,
    LineIdentityRevocationStatus,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LineIdentityBindingView(_StrictModel):
    line_user_id: str
    status: LineIdentityBindingStatus
    version: int
    subject_type: LineBindingSubjectType
    subject_reference: str
    subject_name: str
    updated_at: datetime | None = None
    revocation_request_id: int | None = None
    revocation_status: LineIdentityRevocationStatus | None = None
    revoked_at: datetime | None = None


class LineIdentityBindingPageView(_StrictModel):
    items: list[LineIdentityBindingView]
    total: int
    page: int
    page_size: int


class LineIdentityCurrentFactBindingView(_StrictModel):
    subject_type: LineBindingSubjectType
    subject_reference: str
    subject_name: str
    owner_line_user_id: str | None = None


class LineIdentityCurrentFactReadbackView(_StrictModel):
    line_user_id: str
    root_status: LineIdentityBindingStatus | None = None
    root_version: int | None = None
    root_binding: LineIdentityCurrentFactBindingView | None = None
    owner_projections: list[LineIdentityCurrentFactBindingView]
    findings: list[LineIdentityCurrentFactFinding]
    readback_status: LineIdentityCurrentFactReadbackStatus
    manual_actions: list[str]
    dual_role_persistence_supported: bool


class LineIdentityRevocationPreviewView(_StrictModel):
    binding: LineIdentityBindingView
    default_menu_publication_id: int | None = None
    provider_menu_id: str | None = None
    blockers: list[str]


class LineIdentityReplacementPreviewView(_StrictModel):
    binding: LineIdentityBindingView
    target_subject_reference: str
    target_subject_name: str
    blockers: list[str]


class LineIdentityRevocationRequestView(_StrictModel):
    request_id: int
    line_user_id: str
    subject_type: LineBindingSubjectType
    subject_reference: str
    status: LineIdentityRevocationStatus
    pending_binding_version: int
    publication_id: int
    provider_menu_id: str
    requested_by_actor_id: str
    reason: str
    attempt_count: int
    last_error_code: str | None = None
    last_error_message: str | None = None

    @field_validator("line_user_id", "pending_binding_version", mode="before")
    @classmethod
    def unwrap_value_object(cls, value):
        return getattr(value, "value", value)


class LineIdentityRevocationApplyRequest(_StrictModel):
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class LineIdentityRevocationActionRequest(_StrictModel):
    reason: str = Field(min_length=1, max_length=1000)


class LineIdentityReplacementRequest(_StrictModel):
    expected_version: int = Field(ge=0)
    target_subject_reference: str = Field(min_length=1, max_length=191)
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class UnboundOrderCandidateView(_StrictModel):
    case_no: str
    client_id: int
    client_name: str
    client_phone: str
    start_date: str | None = None
    status: str


class UnboundProvisionalCandidateView(_StrictModel):
    registration_id: int
    name: str
    phone: str
    line_user_id: str
    client_id: int | None = None
    submitted_at: str | None = None


class UnboundPairingCandidatesResponseView(_StrictModel):
    orders: list[UnboundOrderCandidateView]
    provisional_registrations: list[UnboundProvisionalCandidateView]


class PairProvisionalRegistrationRequest(_StrictModel):
    provisional_registration_id: int = Field(gt=0)
    target_case_no: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class PairProvisionalRegistrationResultView(_StrictModel):
    case_no: str
    client_id: int
    client_name: str
    line_user_id: str
    status: str


__all__ = [
    name
    for name in globals()
    if name.startswith("LineIdentity")
    or name.startswith("Unbound")
    or name.startswith("Pair")
]

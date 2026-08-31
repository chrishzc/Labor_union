"""Strict transport models for Client LIFF profile changes and review."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClientProfileLiffIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    line_id_token: str = Field(min_length=1, max_length=4096)


class ClientProfileQueryRequest(ClientProfileLiffIdentity):
    pass


class ClientProfileChangeRequest(ClientProfileLiffIdentity):
    changes: dict[str, str] = Field(min_length=1)
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


class ClientProfileChangeApplyRequest(ClientProfileChangeRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class ClientProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    client_id: int = Field(gt=0)
    version: int = Field(ge=0)
    values: dict[str, str]


class ClientProfilePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    client_id: int = Field(gt=0)
    current_version: int = Field(ge=0)
    before: dict[str, str]
    requested: dict[str, str]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    blockers: list[str]
    apply_ready: bool


class ClientProfileRequestView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: int = Field(gt=0)
    client_id: int = Field(gt=0)
    status: Literal["pending", "approved_applied", "rejected", "outcome_unknown"]
    request_version: int = Field(ge=0)
    profile_version: int = Field(ge=0)
    before: dict[str, str]
    requested: dict[str, str]
    reason: str


class ClientProfileApplicantReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request: ClientProfileRequestView
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
    replayed: bool
    readback: ClientProfileView


class ClientProfileRequestPageView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    items: list[ClientProfileRequestView]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class ClientProfileApprovalPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    expected_request_version: int = Field(ge=0)


class ClientProfileApprovalApplyRequest(ClientProfileApprovalPreviewRequest):
    expected_profile_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)
    reason: str = Field(min_length=1, max_length=500)


class ClientProfileApprovalReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request: ClientProfileRequestView
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
    replayed: bool
    readback: ClientProfileView


class ClientProfileRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    expected_request_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class ClientProfileRejectPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    expected_request_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)

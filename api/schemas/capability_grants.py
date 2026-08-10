"""Typed boundary for capability-grant administration."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CapabilityGrantApplyBody(BaseModel):
    target_admin_user_id: int = Field(gt=0)
    capability: str = Field(min_length=1, max_length=100)
    action: Literal["grant", "revoke"]
    expected_authorization_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)
    expires_at: datetime | None = None


class CapabilityGrantReceiptView(BaseModel):
    target_admin_user_id: int
    capability: str
    action: Literal["grant", "revoke"]
    before_authorization_version: int
    authorization_version: int

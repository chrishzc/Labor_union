"""
File: staff_retirement.py
Description: 定義 Staff lifecycle 的 strict request、preview、query 與獨立 receipt schema。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StaffLifecycleTransitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effective_at: datetime
    reason_code: str = Field(min_length=1, max_length=64)

    @field_validator("effective_at")
    @classmethod
    def require_aware_effective_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("staff_retirement_effective_at_invalid")
        return value


class StaffLifecycleApplyInput(StaffLifecycleTransitionInput):
    expected_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffLifecycleView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    state: Literal["active", "retired"]
    version: int = Field(ge=0)
    effective_at: datetime | None = None
    reason_code: str | None = None


class StaffLifecyclePreviewView(StaffLifecycleView):
    model_config = ConfigDict(extra="forbid")

    after_state: Literal["active", "retired"]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffLifecycleApplyReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    state: Literal["active", "retired"]
    resulting_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)

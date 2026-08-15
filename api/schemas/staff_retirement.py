"""
File: staff_retirement.py
Description: Staff lifecycle API 的 typed request 與 view schema。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StaffLifecycleTransitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effective_at: datetime
    reason_code: str = Field(min_length=1, max_length=64)


class StaffLifecycleApplyInput(StaffLifecycleTransitionInput):
    expected_version: int = Field(ge=0)
    preview_fingerprint: str = Field(min_length=64, max_length=64)


class StaffLifecycleView(BaseModel):
    staff_id: int
    state: Literal["active", "retired"]
    version: int
    effective_at: datetime | None = None
    masked_reason_code: str | None = None


class StaffLifecyclePreviewView(StaffLifecycleView):
    after_state: Literal["active", "retired"]
    preview_fingerprint: str

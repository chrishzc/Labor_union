"""
File: staff_availability.py
Description: 定義 Staff Availability long leave、pause 的 strict HTTP 契約與 receipt。
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from domains.scheduling.staff_availability import (
    StaffAvailabilityAction,
    StaffAvailabilityBlockStatus,
    StaffUnavailabilityKind,
)


class StaffAvailabilityIntentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: StaffAvailabilityAction
    reason: str = Field(min_length=1, max_length=500)
    start_date: date | None = None
    end_date: date | None = None
    block_id: int | None = Field(default=None, gt=0)
    resume_date: date | None = None


class StaffAvailabilityApplyBody(StaffAvailabilityIntentBody):
    expected_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffUnavailabilityBlockView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    kind: StaffUnavailabilityKind
    start_date: date
    end_date: date | None
    status: StaffAvailabilityBlockStatus
    reason: str


class StaffAvailabilityPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    action: StaffAvailabilityAction
    source_version: int = Field(ge=0)
    target_block: StaffUnavailabilityBlockView | None
    candidate_kind: StaffUnavailabilityKind | None
    candidate_start_date: date | None
    candidate_end_date: date | None
    blockers: list[str]
    can_apply: bool
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StaffAvailabilityReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    action: StaffAvailabilityAction
    block: StaffUnavailabilityBlockView
    aggregate_version: int = Field(ge=1)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)


__all__ = [
    "StaffAvailabilityApplyBody",
    "StaffAvailabilityIntentBody",
    "StaffAvailabilityPreviewView",
    "StaffAvailabilityReceiptView",
    "StaffUnavailabilityBlockView",
]

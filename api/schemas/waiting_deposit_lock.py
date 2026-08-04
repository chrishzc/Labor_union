"""Typed HTTP views for waiting-deposit lock Preview and Apply."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WaitingDepositOccupancyView(_StrictModel):
    segment_id: int = Field(..., gt=0)
    staff_id: int = Field(..., gt=0)
    occupancy_date: str
    kind: Literal["service", "buffer"]


class WaitingDepositConflictView(_StrictModel):
    staff_id: int = Field(..., gt=0)
    lock_date: str
    source_type: Literal["assignment", "schedule", "active_lock"]
    source_id: int = Field(..., gt=0)


class WaitingDepositLockPreviewView(_StrictModel):
    case_no: str
    plan_id: int = Field(..., gt=0)
    service_day_count: int = Field(..., ge=0)
    buffer_day_count: int = Field(..., ge=0)
    occupancy: list[WaitingDepositOccupancyView]
    conflicts: list[WaitingDepositConflictView]
    apply_allowed: bool
    preview_fingerprint: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class WaitingDepositLockApplyBody(_StrictModel):
    preview_fingerprint: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class WaitingDepositLockRowView(_StrictModel):
    segment_id: int = Field(..., gt=0)
    staff_id: int = Field(..., gt=0)
    lock_date: str


class WaitingDepositLockReceiptView(_StrictModel):
    result: Literal["created", "existing"]
    lock_id: int = Field(..., gt=0)
    plan_id: int = Field(..., gt=0)
    case_no: str
    lock_rows: list[WaitingDepositLockRowView]


class WaitingDepositLockReleasePreviewView(_StrictModel):
    case_no: str
    plan_id: int = Field(..., gt=0)
    lock_id: int = Field(..., gt=0)
    service_day_count: int = Field(..., gt=0)
    staff_count: int = Field(..., gt=0, le=4)
    apply_allowed: bool
    blockers: list[str]
    preview_fingerprint: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class WaitingDepositLockReleaseApplyBody(_StrictModel):
    preview_fingerprint: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    reason: str = Field(..., min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _require_trimmed_reason(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("reason must not contain surrounding whitespace")
        if not value:
            raise ValueError("reason must be non-empty")
        return value


class WaitingDepositLockReleaseReceiptView(_StrictModel):
    result: Literal["created", "existing"]
    case_no: str
    plan_id: int = Field(..., gt=0)
    lock_id: int = Field(..., gt=0)
    plan_status: Literal["proposed"]
    lock_status: Literal["released"]
    lock_rows: list[WaitingDepositLockRowView]


__all__ = [
    "WaitingDepositConflictView",
    "WaitingDepositLockApplyBody",
    "WaitingDepositLockPreviewView",
    "WaitingDepositLockReleaseApplyBody",
    "WaitingDepositLockReleasePreviewView",
    "WaitingDepositLockReleaseReceiptView",
    "WaitingDepositLockReceiptView",
    "WaitingDepositLockRowView",
    "WaitingDepositOccupancyView",
]

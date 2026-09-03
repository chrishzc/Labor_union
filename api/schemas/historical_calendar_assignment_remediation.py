"""Strict response schemas for historical calendar assignment remediation."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HistoricalCalendarAssignmentPreviewView(_StrictModel):
    case_no: str
    caregiver_ordinal: StrictInt = Field(ge=1)
    order_status: str
    lifecycle_version: StrictInt = Field(ge=0)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_identity: str
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    staff_id: StrictInt | None
    staff_name: str | None
    start_date: date | None
    end_date: date | None
    existing_assignment_id: StrictInt | None
    disposition: str
    blockers: list[str]
    apply_allowed: bool
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalCalendarAssignmentReceiptView(_StrictModel):
    receipt_key: str
    case_no: str
    caregiver_ordinal: StrictInt = Field(ge=1)
    assignment_id: StrictInt
    created: bool
    lifecycle_version: StrictInt = Field(ge=0)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool
    orders_changed: bool = False


__all__ = [
    "HistoricalCalendarAssignmentPreviewView",
    "HistoricalCalendarAssignmentReceiptView",
]

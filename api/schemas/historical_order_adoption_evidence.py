"""Strict read-only HTTP view for immutable Historical Orders adoption evidence."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HistoricalAdoptionPairedStaffEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    caregiver_ordinal: int = Field(ge=1)
    masked_staff_name: str = Field(min_length=1)
    staff_id: int = Field(ge=1)
    resolution: Literal["evidence_only", "assignment_candidate", "assignment_reused"]
    source_start_date: date | None
    source_end_date: date | None
    assignment_id: int | None = Field(default=None, ge=1)


class HistoricalOrderAdoptionEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_no: str = Field(min_length=1, max_length=50)
    receipt_id: int = Field(ge=1)
    receipt_identity: str = Field(min_length=1)
    evidence_owner: Literal["Historical Orders Adoption"]
    source_identity: str = Field(min_length=1)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    historical_source_status: Literal["cancelled", "deposit_paid", "discussion"] | None
    operational_baseline_step: int | None = Field(default=None, ge=1, le=11)
    source_start_date: date | None
    source_end_date: date | None
    source_period_availability: Literal["available", "unavailable"]
    paired_staff: tuple[HistoricalAdoptionPairedStaffEvidenceView, ...]
    paired_staff_availability: Literal["available", "unavailable"]


__all__ = ["HistoricalOrderAdoptionEvidenceView"]

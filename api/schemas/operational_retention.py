"""Typed public contracts for storage-retention Query, Preview and Apply."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetentionSourceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    label: str
    storage_kind: Literal["database", "files"]
    classification: Literal["eligible", "blocked-unclassified"]
    current_logical_bytes: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    expired_count: int = Field(ge=0)
    oldest_eligible_at_utc: datetime | None
    estimated_reclaimable_bytes: int = Field(ge=0)
    high_water_bytes: int | None = Field(default=None, ge=1)
    low_water_bytes: int | None = Field(default=None, ge=1)
    capacity_status: Literal["normal", "high", "unconfigured", "unavailable"]
    blocked_reason: str | None = None
    last_run_at_utc: datetime | None = None
    last_outcome: str | None = None


class RetentionDashboardView(BaseModel):
    policy_revision: str
    retention_days: Literal[30]
    sources: tuple[RetentionSourceView, ...]


class RetentionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=100)
    mode: Literal["expired", "capacity"] = "expired"
    reason: str = Field(min_length=1, max_length=500)
    batch_size: int = Field(default=250, ge=1, le=500)


class RetentionPreviewView(BaseModel):
    policy_revision: str
    source_id: str
    mode: Literal["expired", "capacity"]
    reason: str
    previewed_at_utc: datetime
    cutoff_at_utc: datetime
    batch_size: int
    candidate_count: int
    estimated_reclaimable_bytes: int
    current_logical_bytes: int
    target_low_water_bytes: int | None
    preview_fingerprint: str


class RetentionApplyRequest(RetentionPreviewRequest):
    previewed_at_utc: datetime
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class RetentionReceiptView(BaseModel):
    idempotency_key: str
    source_id: str
    mode: Literal["expired", "capacity"]
    policy_revision: str
    preview_fingerprint: str
    outcome: Literal["completed", "partial", "capacity_unrelieved"]
    candidate_count: int
    deleted_count: int
    failed_count: int
    deleted_logical_bytes: int
    started_at_utc: datetime
    finished_at_utc: datetime
    correlation_id: str
    error_code: str | None
    replayed: bool

"""
File: orders_stage_projection.py
Description: 定義 Orders 七階段與十一作業步驟的嚴格 HTTP read model。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


StageStatus = Literal["not_started", "in_progress", "blocked", "completed", "unavailable"]


class SourceLineageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: str
    identity: str | None
    version: int | None = Field(default=None, ge=0)


class ProjectionNoticeView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class AvailableActionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    method: Literal["GET"]
    path: str


class SettlementProjectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Literal["service_completion", "client_settlement", "staff_payout"]
    status: StageStatus
    source: SourceLineageView
    occurred_at: datetime | None
    availability_reason: str | None


class StageProjectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordinal: int = Field(ge=1, le=7)
    code: Literal["intake_terms", "matching_willingness", "client_review", "contract_deposit", "date_confirmation", "active_service", "settlement_payout"]
    label: str
    owner: str
    status: StageStatus
    source: SourceLineageView
    occurred_at: datetime | None
    blockers: list[ProjectionNoticeView]
    warnings: list[ProjectionNoticeView]
    available_actions: list[AvailableActionView]
    availability_reason: str | None
    settlement: list[SettlementProjectionView]


class SopStepProjectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordinal: int = Field(ge=1, le=11)
    code: str
    label: str
    owner: str
    status: StageStatus
    occurred_at: datetime | None
    blockers: list[ProjectionNoticeView]
    warnings: list[ProjectionNoticeView]
    available_actions: list[AvailableActionView]
    availability_reason: str | None


class OrderOperationalTimelineView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    base_revision: int = Field(ge=0)
    current_stage_code: Literal["intake_terms", "matching_willingness", "client_review", "contract_deposit", "date_confirmation", "active_service", "settlement_payout"] | None
    current_sop_step: int | None = Field(default=None, ge=1, le=11)
    terminal_state: Literal["cancelled"] | None = None
    stages: list[StageProjectionView] = Field(min_length=7, max_length=7)
    sop_steps: list[SopStepProjectionView] = Field(min_length=11, max_length=11)
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class StageCountsView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intake_terms: int = Field(ge=0)
    matching_willingness: int = Field(ge=0)
    client_review: int = Field(ge=0)
    contract_deposit: int = Field(ge=0)
    date_confirmation: int = Field(ge=0)
    active_service: int = Field(ge=0)
    settlement_payout: int = Field(ge=0)


class OrderOperationalTimelinePageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[OrderOperationalTimelineView]
    stage_counts: StageCountsView
    next_cursor: str | None
    etag: str = Field(pattern=r"^[0-9a-f]{64}$")


__all__ = ["OrderOperationalTimelinePageView"]

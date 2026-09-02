"""
File: orders_core_stage_projection.py
Description: 定義待辦看板 Beta 十三核心階段的嚴格唯讀 HTTP contract。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from subsystems.orders.core_stage_filter_query import (
    CoreStageSubstatusCode,
    HistoricalLifecycleFacet,
)


StageStatusView = Literal["not_started", "in_progress", "blocked", "completed", "unavailable"]
CoreStageBranchTypeView = Literal["normal", "historical", "cancelled"]
CoreStageCodeView = Literal[
    "intake_validation",
    "matching_pool",
    "caregiver_line_delivery",
    "caregiver_willingness_reply",
    "formal_recommendation",
    "caregiver_contract",
    "deposit_settlement",
    "client_contract",
    "confirmed_service_dates",
    "formal_service",
    "service_completion",
    "client_settlement",
    "staff_payout",
]
CoreStageSubstatusCodeView = CoreStageSubstatusCode
HistoricalLifecycleFacetView = HistoricalLifecycleFacet
OrderLifecycleStatusView = Literal[
    "待補件", "洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消",
    "歷史訂單－未服務", "歷史訂單－服務中", "歷史訂單－服務完成", "歷史訂單－帳務完成",
]


class CoreStageSourceLineageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: str
    identity: str | None
    version: int | None = Field(default=None, ge=0)


class CoreStageNoticeView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class CoreStageReadActionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    method: Literal["GET"]
    path: str


class CoreStageProjectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordinal: int = Field(ge=1, le=13)
    code: CoreStageCodeView
    label: str
    owner: str
    status: StageStatusView
    substatus_code: CoreStageSubstatusCodeView
    source: CoreStageSourceLineageView
    occurred_at: datetime | None
    blockers: list[CoreStageNoticeView]
    warnings: list[CoreStageNoticeView]
    available_read_actions: list[CoreStageReadActionView]
    availability_reason: str | None


class OrderCoreStageTimelineView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    base_revision: int = Field(ge=0)
    lifecycle_status: OrderLifecycleStatusView
    branch_type: CoreStageBranchTypeView
    current_core_stage_code: CoreStageCodeView | None
    current_core_stage_ordinal: int | None = Field(default=None, ge=1, le=13)
    historical_current_owner_stage_code: CoreStageCodeView | None
    historical_current_owner_stage_ordinal: int | None = Field(default=None, ge=1, le=13)
    core_stages: list[CoreStageProjectionView] = Field(min_length=13, max_length=13)
    source_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalLifecycleCountsView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unserved: int = Field(ge=0)
    in_service: int = Field(ge=0)
    service_completed: int = Field(ge=0)
    accounting_completed: int = Field(ge=0)


class OrderCoreStageTimelinePageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[OrderCoreStageTimelineView]
    stage_counts: dict[CoreStageCodeView, int] = Field(default_factory=dict)
    substatus_counts: dict[CoreStageSubstatusCodeView, int] = Field(default_factory=dict)
    historical_lifecycle_counts: HistoricalLifecycleCountsView = Field(
        default_factory=lambda: HistoricalLifecycleCountsView(
            unserved=0,
            in_service=0,
            service_completed=0,
            accounting_completed=0,
        )
    )
    next_cursor: str | None
    etag: str = Field(pattern=r"^[0-9a-f]{64}$")


class TerminalCompletionComponentView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    owner: str
    completed: bool
    reason: str | None


class OrderTerminalAggregateView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str
    applicable: bool
    fully_closed: bool
    components: list[TerminalCompletionComponentView]


class OrderTerminalAggregatePageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[OrderTerminalAggregateView]
    next_cursor: str | None


__all__ = ["OrderCoreStageTimelinePageView", "OrderTerminalAggregatePageView"]

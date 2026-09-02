"""
File: orders_core_stage_projection.py
Description: 定義待辦看板 Beta 十三核心階段的嚴格唯讀 HTTP contract。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
CoreStageSubstatusCodeView = Literal[
    "intake_pending", "intake_in_progress", "intake_blocked", "data_complete", "intake_unavailable",
    "candidate_pool_pending", "candidate_pool_building", "candidate_pool_blocked", "candidate_pool_ready", "candidate_pool_unavailable",
    "contact_pending", "contact_in_progress", "contact_blocked", "contact_completed", "contact_unavailable",
    "reply_pending", "reply_partial", "reply_blocked", "reply_complete", "reply_unavailable",
    "recommendation_pending", "recommendation_in_progress", "recommendation_blocked", "recommendation_completed", "recommendation_unavailable",
    "caregiver_contract_pending", "caregiver_contract_signing", "caregiver_contract_blocked", "caregiver_contract_completed", "caregiver_contract_unavailable",
    "deposit_pending", "deposit_in_progress", "deposit_blocked", "deposit_settled", "deposit_unavailable",
    "client_contract_pending", "client_contract_signing", "client_contract_blocked", "client_contract_completed", "client_contract_unavailable",
    "date_confirmation_pending", "date_confirmation_in_progress", "date_confirmation_blocked", "date_confirmed", "date_confirmation_unavailable",
    "waiting_to_start", "service_in_progress", "service_blocked", "service_period_completed", "service_schedule_unavailable",
    "completion_pending", "completion_in_progress", "completion_blocked", "completion_confirmed", "completion_record_missing",
    "client_settlement_pending", "client_settlement_in_progress", "client_balance_open", "client_settled", "client_settlement_unavailable",
    "staff_settlement_pending", "staff_settlement_in_progress", "staff_payable_open", "staff_settled", "staff_settlement_unavailable",
]
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
    core_stages: list[CoreStageProjectionView] = Field(min_length=13, max_length=13)
    source_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class OrderCoreStageTimelinePageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[OrderCoreStageTimelineView]
    next_cursor: str | None
    etag: str = Field(pattern=r"^[0-9a-f]{64}$")


__all__ = ["OrderCoreStageTimelinePageView"]

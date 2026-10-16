"""
File: line_order_groups.py
Description: 定義 LINE 訂單群組、不可變事件與 numbered observation HTTP schemas。
"""

from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from domains.line.order_group import LineOrderGroupBindingStatus


class LineOrderGroupRecord(BaseModel):
    case_no: str
    group_id: str | None
    status: str
    version: int


class LineOrderGroupPageResponse(BaseModel):
    items: list[LineOrderGroupRecord]
    total: int


class LineOrderGroupNumberedPageResponse(LineOrderGroupPageResponse):
    page: int
    page_size: int
    total_pages: int


class LineOrderGroupEventResponse(BaseModel):
    event_id: int
    case_no: str
    event_type: str
    actor_id: str
    occurred_at: datetime
    invitation_fingerprint: str | None = Field(
        default=None,
        description="邀請網址的不可逆指紋；API 永不回傳邀請網址原文。",
    )


class LineOrderGroupEventPageResponse(BaseModel):
    items: list[LineOrderGroupEventResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class LineOrderGroupParticipantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    role: Literal["customer", "staff"]
    name: str | None
    membership_status: Literal["joined", "left", "pending", "unknown"]
    staff_union_no: str | None = None


class LineOrderGroupWorkspaceEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    event_key: str
    case_no: str
    event_type: str
    occurred_at: datetime
    participant_role: Literal["customer", "staff"] | None
    participant_name: str | None
    participant_union_no: str | None = None


class LineOrderGroupWorkspaceRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    case_no: str
    status: LineOrderGroupBindingStatus
    customer_name: str | None
    bound_at: datetime | None
    last_invitation_at: datetime | None
    members: list[LineOrderGroupParticipantResponse]
    latest_event: LineOrderGroupWorkspaceEventResponse | None


class LineOrderGroupWorkspacePageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    items: list[LineOrderGroupWorkspaceRecordResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class LineOrderGroupWorkspaceEventPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    items: list[LineOrderGroupWorkspaceEventResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


__all__ = [
    "LineOrderGroupEventResponse",
    "LineOrderGroupEventPageResponse",
    "LineOrderGroupNumberedPageResponse",
    "LineOrderGroupPageResponse",
    "LineOrderGroupRecord",
]

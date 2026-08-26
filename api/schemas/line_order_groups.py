"""
File: line_order_groups.py
Description: 定義 LINE 訂單群組、不可變事件與 numbered observation HTTP schemas。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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


__all__ = [
    "LineOrderGroupEventResponse",
    "LineOrderGroupEventPageResponse",
    "LineOrderGroupNumberedPageResponse",
    "LineOrderGroupPageResponse",
    "LineOrderGroupRecord",
]

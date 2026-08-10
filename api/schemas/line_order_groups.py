"""HTTP schemas for LINE order-group status and immutable event history."""

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


__all__ = [
    "LineOrderGroupEventResponse",
    "LineOrderGroupPageResponse",
    "LineOrderGroupRecord",
]

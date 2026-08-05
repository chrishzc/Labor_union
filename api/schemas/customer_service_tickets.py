"""Schemas for LINE customer service tickets."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TicketUpdateRequest(BaseModel):
    status: str | None = Field(default=None)
    internal_note: str | None = Field(default=None, max_length=4000)


class TicketReplyRequest(BaseModel):
    reply_text: str = Field(min_length=1, max_length=2000)
    internal_note: str | None = Field(default=None, max_length=4000)
    resolve: bool = False


class ClientProfileFieldUpdateRequest(BaseModel):
    field: str = Field(min_length=1, max_length=80)
    action: str = Field(pattern="^(add|update|clear)$")
    value: str | int | None = None
    note: str | None = Field(default=None, max_length=1000)

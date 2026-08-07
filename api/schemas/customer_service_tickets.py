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
    reviewer_name: str = Field(min_length=1, max_length=100)
    decision: str = Field(default="approve", pattern="^(approve|reject)$")
    rejection_reason: str | None = Field(default=None, max_length=1000)


class ProfileChangeItem(BaseModel):
    field_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    value: str | int = Field()


class ProfileChangeSubmitRequest(BaseModel):
    line_user_id: str = ""
    line_id_token: str = ""
    changes: list[ProfileChangeItem] = Field(min_length=1)


class ProfileChangeRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    reviewer_name: str = Field(min_length=1, max_length=100)


class ProfileChangeApproveRequest(BaseModel):
    reviewer_name: str = Field(min_length=1, max_length=100)
    approved_field_ids: list[str] | None = None
    rejection_reason: str | None = Field(default=None, max_length=1000)


class ProfileChangeRevertRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    reviewer_name: str = Field(min_length=1, max_length=100)

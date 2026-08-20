"""
File: customer_service.py
Description: 定義客服查詢、結案 Preview／Apply 與既有回覆端點的嚴格 HTTP 契約。
"""

from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus


class CustomerServiceTicketView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: int
    line_user_id_masked: str
    category: CustomerServiceCategory
    status: CustomerServiceStatus
    version: int
    client_id: int | None = None
    case_no: str | None = None
    client_name: str | None = None
    client_phone: str | None = None
    assigned_admin_user_id: int | None = None
    internal_note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CustomerServiceEventView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    event_type: str
    message_text: str | None = None
    actor_id: str
    created_at: datetime


class CustomerServiceDetailView(BaseModel):
    ticket: CustomerServiceTicketView
    events: list[CustomerServiceEventView]


class CustomerServicePageView(BaseModel):
    items: list[CustomerServiceTicketView]
    total: int
    page: int
    page_size: int


class CustomerServiceSummaryView(BaseModel):
    waiting: int
    handling: int
    resolved_today: int


class CustomerServiceUpdatePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["resolved"]
    internal_note: str | None = Field(max_length=4000)
    expected_version: int = Field(ge=0)


class CustomerServiceUpdateApplyRequest(CustomerServiceUpdatePreviewRequest):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class CustomerServiceUpdatePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: int
    before_status: CustomerServiceStatus
    after_status: CustomerServiceStatus
    current_version: int = Field(ge=0)
    expected_version: int = Field(ge=0)
    blockers: list[str]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    apply_ready: bool


class CustomerServiceUpdateRequest(BaseModel):
    status: CustomerServiceStatus
    internal_note: str | None = Field(default=None, max_length=4000)
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=191)


class CustomerServiceReplyRequest(BaseModel):
    reply_text: str = Field(min_length=1, max_length=2000)
    resolve: bool = False
    internal_note: str | None = Field(default=None, max_length=4000)
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=191)

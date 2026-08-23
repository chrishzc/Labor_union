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


class HumanEscalationClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    expected_escalation_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class HumanEscalationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    source_event_identity: str = Field(min_length=1, max_length=191)
    source_kind: Literal["ticket_referral", "line_inbox", "binding_failure", "runtime_health"]
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    trigger_code: Literal[
        "explicit_human_request",
        "explicit_wrong_answer",
        "binding_failure_threshold_2",
        "complaint",
        "runtime_critical",
    ]
    trigger_policy_version: str = Field(min_length=1, max_length=191)
    ticket_category: Literal[
        "service_flow",
        "payment_subsidy",
        "service_progress",
        "profile_update",
        "contact_union",
        "other",
    ]
    masked_context: dict[str, str]
    hold_scope: str = Field(min_length=1, max_length=191)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)

    def model_post_init(self, __context) -> None:
        if set(self.masked_context) != {
            "summary_code",
            "policy_version",
            "category",
            "redaction_version",
        }:
            raise ValueError("masked_context must use the closed M4 allowlist")


class HumanEscalationHandlingRequest(HumanEscalationClaimRequest):
    expected_ticket_version: int = Field(ge=0)


class HumanEscalationResolveRequest(HumanEscalationHandlingRequest):
    resolution_code: str = Field(min_length=1, max_length=64)
    resolution_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class HumanEscalationReceiptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    receipt_id: str
    command_family: str
    operation: str
    escalation_id: int = Field(gt=0)
    ticket_ref: str
    resulting_workflow_status: str
    resulting_hold_state: str
    current_version: str
    replayed: bool
    correlation_id: str
    committed_at: datetime


class HumanEscalationViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    escalation_id: int = Field(gt=0)
    ticket_ref: str
    category: str
    urgency: str
    trigger_code: str
    workflow_status: str
    workflow_version: int = Field(ge=0)
    automation_hold: str
    hold_scope_label: str
    masked_context: dict[str, str]
    alert_status: str
    current_version: str
    created_at: datetime
    updated_at: datetime
    available_actions: list[str]

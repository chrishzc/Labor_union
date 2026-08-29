"""
File: line_tasks.py
Description: 定義 LINE Delivery 控制輸入與 server-masked 查詢輸出模型。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from domains.line.delivery import LineDeliveryStatus


class LineTaskActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=191)
    correlation_id: str = Field(default="", max_length=191)


class LineDeliveryPublicSourceType(StrEnum):
    GENERAL_PUSH = "general_push"
    CUSTOMER_SERVICE = "customer_service"
    CONTRACT = "contract"
    FOLLOW_SCHEDULE = "follow_schedule"
    IDENTITY = "identity"
    IDENTITY_REVIEW = "identity_review"
    RICH_MENU = "rich_menu"
    RICH_MENU_LINK = "rich_menu_link"
    RICH_MENU_UNLINK = "rich_menu_unlink"
    WEBHOOK = "webhook"
    GROUP_INVITATION = "group_invitation"
    RUNTIME = "runtime"
    MATCHING = "matching"
    ORDER = "order"
    FINANCE = "finance"
    ASSIGNMENT = "assignment"


class LineDeliveryWorkerStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    STOPPED = "stopped"
    MISSING = "missing"
    UNKNOWN = "unknown"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LineDeliveryPublicSummaryView(_StrictModel):
    total: int
    pending: int
    processing: int
    sent: int
    retryable_failed: int
    failed: int
    cancelled: int
    overdue: int
    sent_today: int
    next_run_at: datetime | None
    worker_running: bool
    worker_status: LineDeliveryWorkerStatus = Field(strict=False)


class LineDeliveryPublicItemView(_StrictModel):
    id: int
    task_id: int
    task_type: str
    source_type: LineDeliveryPublicSourceType
    status: LineDeliveryStatus = Field(strict=False)
    scheduled_at: datetime
    completed_attempts: int
    max_attempts: int
    next_retry_at: datetime | None
    sent_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LineDeliveryPublicAttemptView(_StrictModel):
    attempt_number: int
    outcome: str
    retry_after_seconds: int | None
    started_at: datetime
    completed_at: datetime


class LineDeliveryPublicPageView(_StrictModel):
    items: list[LineDeliveryPublicItemView]
    page: int
    page_size: int
    total: int
    total_pages: int


class LineDeliveryPublicDetailView(_StrictModel):
    task: LineDeliveryPublicItemView
    attempts: list[LineDeliveryPublicAttemptView]


class LineDeliveryTaskActionResultView(_StrictModel):
    """Masked typed readback returned after a task control operation."""

    id: int = Field(gt=0)
    task_id: int = Field(gt=0)
    task_type: str = Field(min_length=1, max_length=191)
    message_kind: str = Field(min_length=1, max_length=191)
    scheduled_at: datetime
    status: LineDeliveryStatus = Field(strict=False)
    completed_attempts: int = Field(ge=0)


__all__ = [
    "LineDeliveryPublicAttemptView",
    "LineDeliveryPublicDetailView",
    "LineDeliveryPublicItemView",
    "LineDeliveryPublicPageView",
    "LineDeliveryPublicSourceType",
    "LineDeliveryPublicSummaryView",
    "LineDeliveryTaskActionResultView",
    "LineDeliveryWorkerStatus",
    "LineTaskActionRequest",
]

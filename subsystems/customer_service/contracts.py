"""
File: contracts.py
Description: 定義客服查詢、結案與回覆 Preview／Apply 的框架無關型別契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey


@dataclass(frozen=True, slots=True)
class CreateCustomerServiceMessage:
    line_user_id: str
    category: CustomerServiceCategory
    message: str
    event_key: str
    client_id: int | None = None
    case_no: str | None = None


@dataclass(frozen=True, slots=True)
class CustomerServiceListQuery:
    status: CustomerServiceStatus | None = CustomerServiceStatus.WAITING
    category: CustomerServiceCategory | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 25


class CustomerServiceReminderSource(StrEnum):
    HANDOFF = "handoff"
    COMPLAINT = "complaint"
    FEEDBACK = "feedback"
    ORDER = "order"
    SERVICE = "service"
    BINDING = "binding"
    UNKNOWN = "unknown"


CustomerServiceReminderStatus = Literal["open", "waiting", "handling"]


@dataclass(frozen=True, slots=True)
class CustomerServiceReminderQuery:
    status: CustomerServiceReminderStatus = "open"
    source: CustomerServiceReminderSource | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 25

    def __post_init__(self) -> None:
        if self.status not in ("open", "waiting", "handling"):
            raise ValueError("invalid customer service reminder status")
        if self.source is not None and not isinstance(self.source, CustomerServiceReminderSource):
            raise ValueError("invalid customer service reminder source")
        if self.page < 1 or not 1 <= self.page_size <= 100:
            raise ValueError("invalid customer service reminder page")


@dataclass(frozen=True, slots=True)
class CustomerServiceReminder:
    ticket_id: int
    client_name: str | None
    case_no: str | None
    status: Literal["waiting", "handling"]
    assigned_admin_name: str | None
    source: CustomerServiceReminderSource
    sources: tuple[CustomerServiceReminderSource, ...]
    reason: str
    is_priority: bool
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CustomerServiceReminderSummary:
    waiting: int
    handling: int


@dataclass(frozen=True, slots=True)
class CustomerServiceReminderPage:
    items: tuple[CustomerServiceReminder, ...]
    total: int
    page: int
    page_size: int
    summary: CustomerServiceReminderSummary


@dataclass(frozen=True, slots=True)
class PreviewCustomerServiceTicketUpdate:
    ticket_id: int
    status: CustomerServiceStatus
    internal_note: str | None
    expected_version: ExpectedVersion
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ApplyCustomerServiceTicketUpdate:
    ticket_id: int
    status: CustomerServiceStatus
    internal_note: str | None
    expected_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    actor_id: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class CustomerServiceTicketUpdatePreview:
    ticket_id: int
    before_status: CustomerServiceStatus
    after_status: CustomerServiceStatus
    current_version: int
    expected_version: int
    blockers: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint
    apply_ready: bool


@dataclass(frozen=True, slots=True)
class CustomerServiceTicketUpdateResult:
    ticket_id: int
    resulting_status: CustomerServiceStatus
    resulting_version: int
    preview_fingerprint: PreviewFingerprint
    replayed: bool
    readback: dict


@dataclass(frozen=True, slots=True)
class PreviewCustomerServiceTicketReply:
    ticket_id: int
    reply_text: str
    resolve: bool
    internal_note: str | None
    expected_version: ExpectedVersion
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ApplyCustomerServiceTicketReply:
    ticket_id: int
    reply_text: str
    resolve: bool
    internal_note: str | None
    expected_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    actor_id: str
    admin_user_id: int | None
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class CustomerServiceTicketReplyPreview:
    ticket_id: int
    before_status: CustomerServiceStatus
    after_status: CustomerServiceStatus
    current_version: int
    expected_version: int
    reply_character_count: int
    will_enqueue_delivery: bool
    preview_fingerprint: PreviewFingerprint
    apply_ready: bool


@dataclass(frozen=True, slots=True)
class CustomerServiceTicketReplyResult:
    ticket_id: int
    resulting_status: CustomerServiceStatus
    resulting_version: int
    preview_fingerprint: PreviewFingerprint
    delivery_enqueued: bool
    delivery_delivered: bool
    replayed: bool
    readback: dict


__all__ = [
    "ApplyCustomerServiceTicketUpdate",
    "ApplyCustomerServiceTicketReply",
    "CreateCustomerServiceMessage",
    "CustomerServiceListQuery",
    "CustomerServiceTicketReplyPreview",
    "CustomerServiceTicketReplyResult",
    "CustomerServiceTicketUpdatePreview",
    "CustomerServiceTicketUpdateResult",
    "PreviewCustomerServiceTicketReply",
    "PreviewCustomerServiceTicketUpdate",
]

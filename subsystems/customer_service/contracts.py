"""
File: contracts.py
Description: 定義客服查詢、結案與回覆 Preview／Apply 的框架無關型別契約。
"""

from __future__ import annotations

from dataclasses import dataclass

from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey


@dataclass(frozen=True, slots=True)
class CreateCustomerServiceMessage:
    line_user_id: str
    category: CustomerServiceCategory
    message: str
    event_key: str


@dataclass(frozen=True, slots=True)
class CustomerServiceListQuery:
    status: CustomerServiceStatus | None = CustomerServiceStatus.WAITING
    category: CustomerServiceCategory | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 25


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

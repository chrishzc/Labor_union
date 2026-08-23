"""
File: delivery_admin_contracts.py
Description: 定義 LINE Delivery 查詢、公開篩選與控制命令契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domains.line.delivery import LineDeliveryStatus
from domains.line.identities import LineDeliveryTaskId
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_positive_integer

_MAXIMUM_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class LineDeliveryAdminQuery:
    statuses: tuple[LineDeliveryStatus, ...] = ()
    source_aggregate_type: str | None = None
    source_aggregate_types: tuple[str, ...] = ()
    recipient_identity: str | None = None
    scheduled_from: datetime | None = None
    scheduled_to: datetime | None = None
    page: int = 1
    page_size: int = 25

    def __post_init__(self) -> None:
        if any(not isinstance(item, LineDeliveryStatus) for item in self.statuses):
            raise TypeError("LINE delivery status filter is invalid")
        require_positive_integer(self.page, "LINE delivery page")
        require_positive_integer(self.page_size, "LINE delivery page size")
        if self.page_size > _MAXIMUM_PAGE_SIZE:
            raise ValueError("LINE delivery page size exceeds maximum")
        if self.source_aggregate_type is not None:
            require_canonical_text(
                self.source_aggregate_type,
                "LINE source aggregate type",
                191,
            )
        if self.source_aggregate_type is not None and self.source_aggregate_types:
            raise ValueError("LINE delivery source filters are ambiguous")
        for source_type in self.source_aggregate_types:
            require_canonical_text(source_type, "LINE source aggregate type", 191)
        if len(set(self.source_aggregate_types)) != len(self.source_aggregate_types):
            raise ValueError("LINE delivery source filters must be unique")
        if self.recipient_identity is not None:
            require_canonical_text(
                self.recipient_identity,
                "LINE recipient identity",
                191,
            )
        for value in (self.scheduled_from, self.scheduled_to):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("LINE delivery date filter must be timezone-aware")
        if (
            self.scheduled_from is not None
            and self.scheduled_to is not None
            and self.scheduled_to < self.scheduled_from
        ):
            raise ValueError("LINE delivery date range is invalid")


@dataclass(frozen=True, slots=True)
class LineDeliveryAdminRecord:
    task_id: LineDeliveryTaskId
    recipient_type: str
    recipient_identity: str
    message_kind: str
    payload_json: str
    status: LineDeliveryStatus
    scheduled_at: datetime
    source_aggregate_type: str
    source_aggregate_identity: str
    completed_attempts: int
    maximum_attempts: int
    next_attempt_at: datetime | None
    provider_message_id: str | None
    error_code: str | None
    error_message: str | None
    sent_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class LineDeliveryAttemptRecord:
    attempt_number: int
    outcome: str
    provider_outcome_type: str
    provider_message_id: str | None
    error_code: str | None
    error_message: str | None
    retry_after_seconds: int | None
    started_at: datetime
    completed_at: datetime
    correlation_id: str


@dataclass(frozen=True, slots=True)
class LineDeliveryAdminPage:
    items: tuple[LineDeliveryAdminRecord, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class ControlLineDeliveryTaskCommand:
    task_id: LineDeliveryTaskId
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "LINE delivery control reason", 500)


__all__ = [
    "ControlLineDeliveryTaskCommand",
    "LineDeliveryAdminPage",
    "LineDeliveryAdminQuery",
    "LineDeliveryAdminRecord",
    "LineDeliveryAttemptRecord",
]

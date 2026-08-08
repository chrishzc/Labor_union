"""Typed application contracts for LINE webhook intake and consumption."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineWebhookEventId
from domains.line.webhook import (
    CanonicalLineWebhookEvent,
    LineWebhookInboxSnapshot,
    LineWebhookLease,
    LineWebhookProcessingStatus,
)
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey


class LineWebhookRegistrationOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class AcceptLineWebhookEventCommand:
    event: CanonicalLineWebhookEvent
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class AcceptLineWebhookEventResult:
    outcome: LineWebhookRegistrationOutcome
    event_id: LineWebhookEventId
    status: LineWebhookProcessingStatus
    version: ExpectedVersion


@dataclass(frozen=True, slots=True)
class ConsumeLineWebhookEventCommand:
    event_id: LineWebhookEventId
    expected_version: ExpectedVersion
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ConsumeLineWebhookEventResult:
    event_id: LineWebhookEventId
    status: LineWebhookProcessingStatus
    resulting_version: ExpectedVersion


@dataclass(frozen=True, slots=True)
class ClaimLineWebhookEventsQuery:
    lease_owner: str
    now: datetime
    batch_size: int = 25

    def __post_init__(self) -> None:
        if not self.lease_owner.strip():
            raise ValueError("LINE webhook lease owner is required")
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("LINE webhook claim time must be timezone-aware")
        if not 1 <= self.batch_size <= 100:
            raise ValueError("LINE webhook batch size must be between 1 and 100")


@dataclass(frozen=True, slots=True)
class CompleteLineWebhookEventCommand:
    event: LineWebhookInboxSnapshot
    lease: LineWebhookLease
    target_status: LineWebhookProcessingStatus
    completed_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.event.event.event_id != self.lease.event_id:
            raise ValueError("LINE webhook completion lease does not match event")
        allowed = {
            LineWebhookProcessingStatus.PROCESSED,
            LineWebhookProcessingStatus.IGNORED,
            LineWebhookProcessingStatus.RETRYABLE_FAILED,
            LineWebhookProcessingStatus.TERMINAL_FAILED,
        }
        if self.target_status not in allowed:
            raise ValueError("LINE webhook completion target is invalid")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("LINE webhook completion time must be timezone-aware")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("LINE webhook retry delay cannot be negative")


__all__ = [
    "AcceptLineWebhookEventCommand",
    "AcceptLineWebhookEventResult",
    "ClaimLineWebhookEventsQuery",
    "CompleteLineWebhookEventCommand",
    "ConsumeLineWebhookEventCommand",
    "ConsumeLineWebhookEventResult",
    "LineWebhookRegistrationOutcome",
]

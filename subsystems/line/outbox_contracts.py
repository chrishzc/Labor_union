"""Typed leases and completion contracts for canonical LINE domain outbox work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shared_kernel.validation import require_canonical_text, require_positive_integer


@dataclass(frozen=True, slots=True)
class ClaimLineOutboxQuery:
    lease_owner: str
    now: datetime
    batch_size: int = 10

    def __post_init__(self) -> None:
        require_canonical_text(self.lease_owner, "LINE outbox lease owner", 191)
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("LINE outbox claim time must be timezone-aware")
        require_positive_integer(self.batch_size, "LINE outbox batch size")
        if self.batch_size > 50:
            raise ValueError("LINE outbox batch size exceeds maximum")


@dataclass(frozen=True, slots=True)
class LineOutboxWorkItem:
    outbox_id: int
    aggregate_type: str
    aggregate_identity: str
    intent_type: str
    payload_json: str
    attempt_count: int
    maximum_attempts: int
    lease_owner: str
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class CompleteLineOutboxCommand:
    work_item: LineOutboxWorkItem
    completed_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    retry_after_seconds: int = 15

    def __post_init__(self) -> None:
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("LINE outbox completion time must be timezone-aware")
        if self.retry_after_seconds < 0:
            raise ValueError("LINE outbox retry delay cannot be negative")

    @property
    def succeeded(self) -> bool:
        return self.error_code is None and self.error_message is None


__all__ = [
    "ClaimLineOutboxQuery",
    "CompleteLineOutboxCommand",
    "LineOutboxWorkItem",
]

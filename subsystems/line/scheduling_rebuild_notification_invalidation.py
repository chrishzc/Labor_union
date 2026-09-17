"""
File: scheduling_rebuild_notification_invalidation.py
Description: 消費排班重建 outbox，取消已被替換月嫂的未送出服務日日誌提醒。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SchedulingRebuildOutboxItem:
    outbox_id: int
    cancelled_assignment_ids: tuple[int, ...]


class SchedulingRebuildNotificationInvalidationError(RuntimeError):
    """A rebuild invalidation failed after its retry state was recorded."""

    def __init__(self, processed: int, error: Exception) -> None:
        super().__init__(
            f"scheduling_rebuild_notification_invalidation_failed:{type(error).__name__}"
        )
        self.processed = processed
        self.error_type = type(error).__name__


class SchedulingRebuildOutboxPort(Protocol):
    def claim_due(self, now: datetime, limit: int) -> tuple[SchedulingRebuildOutboxItem, ...]: ...
    def mark_published(self, outbox_id: int) -> None: ...
    def mark_retry_or_failed(self, outbox_id: int, now: datetime, error: Exception) -> None: ...


class NotificationInvalidationPort(Protocol):
    def cancel_service_day_log_reminders_for_assignments(self, assignment_ids: tuple[int, ...]) -> int: ...


class SchedulingRebuildNotificationInvalidationProjector:
    def __init__(
        self,
        outbox: SchedulingRebuildOutboxPort,
        notifications: NotificationInvalidationPort,
    ) -> None:
        self._outbox = outbox
        self._notifications = notifications

    def run_once(self, now: datetime, *, limit: int = 100) -> int:
        processed = 0
        first_error: Exception | None = None
        for item in self._outbox.claim_due(now, limit):
            try:
                self._notifications.cancel_service_day_log_reminders_for_assignments(
                    item.cancelled_assignment_ids
                )
                self._outbox.mark_published(item.outbox_id)
            except Exception as error:
                self._outbox.mark_retry_or_failed(item.outbox_id, now, error)
                if first_error is None:
                    first_error = error
            processed += 1
        if first_error is not None:
            # The worker commits retry/failure state, then re-raises this signal
            # so stale-assignment reminders cannot cross the provider boundary.
            raise SchedulingRebuildNotificationInvalidationError(
                processed, first_error
            )
        return processed


__all__ = [
    "SchedulingRebuildNotificationInvalidationError",
    "SchedulingRebuildNotificationInvalidationProjector",
    "SchedulingRebuildOutboxItem",
]

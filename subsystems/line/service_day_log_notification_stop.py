"""
File: service_day_log_notification_stop.py
Description: 消費 Scheduling 已提交的服務日日誌 outbox，停止同一服務日尚未送出的 LINE 提醒。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ServiceDayLogOutboxItem:
    outbox_id: int
    assignment_id: int
    service_date: str


class ServiceDayLogOutboxPort(Protocol):
    def claim_due(self, now: datetime, limit: int) -> tuple[ServiceDayLogOutboxItem, ...]: ...
    def mark_published(self, outbox_id: int) -> None: ...
    def mark_retry_or_failed(self, outbox_id: int, now: datetime, error: Exception) -> None: ...


class NotificationStopPort(Protocol):
    def cancel_service_day_log_reminders(self, assignment_id: int, service_date: str) -> int: ...


class ServiceDayLogNotificationStopProjector:
    def __init__(self, outbox: ServiceDayLogOutboxPort, notifications: NotificationStopPort) -> None:
        self._outbox = outbox
        self._notifications = notifications

    def run_once(self, now: datetime, *, limit: int = 100) -> int:
        processed = 0
        for item in self._outbox.claim_due(now, limit):
            try:
                self._notifications.cancel_service_day_log_reminders(
                    item.assignment_id, item.service_date
                )
                self._outbox.mark_published(item.outbox_id)
            except Exception as error:
                self._outbox.mark_retry_or_failed(item.outbox_id, now, error)
            processed += 1
        return processed


__all__ = ["ServiceDayLogNotificationStopProjector", "ServiceDayLogOutboxItem"]

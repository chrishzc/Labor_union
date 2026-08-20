"""
File: scheduling_checkpoint_notification_source.py
Description: 將 Scheduling 服務結束 checkpoint outbox 投影為 LINE immutable source event，失敗最多三次、每次相隔一秒。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol

from subsystems.line.notification_source_adapters import (
    from_scheduling_service_day_checkpoint_outbox,
)


@dataclass(frozen=True, slots=True)
class SchedulingCheckpointOutboxItem:
    outbox_id: int
    event_id: int
    payload: Mapping[str, object]
    occurred_at: datetime


class SchedulingCheckpointOutboxPort(Protocol):
    def claim_due(self, now: datetime, limit: int) -> tuple[SchedulingCheckpointOutboxItem, ...]: ...
    def mark_published(self, outbox_id: int) -> None: ...
    def mark_retry_or_failed(self, outbox_id: int, now: datetime, error: Exception) -> None: ...


class NotificationSourceRegistryPort(Protocol):
    def register_source_event(self, event) -> int: ...


class SchedulingCheckpointNotificationSourceProjector:
    def __init__(self, outbox: SchedulingCheckpointOutboxPort, registry: NotificationSourceRegistryPort) -> None:
        self._outbox = outbox
        self._registry = registry

    def run_once(self, now: datetime, *, limit: int = 100) -> int:
        processed = 0
        for item in self._outbox.claim_due(now, limit):
            try:
                event = from_scheduling_service_day_checkpoint_outbox(
                    outbox_id=item.outbox_id,
                    event_id=item.event_id,
                    payload=item.payload,
                    occurred_at=item.occurred_at,
                )
                register_and_project = getattr(self._registry, "register_and_project", None)
                if callable(register_and_project):
                    register_and_project(event)
                else:
                    self._registry.register_source_event(event)
                self._outbox.mark_published(item.outbox_id)
            except Exception as error:
                self._outbox.mark_retry_or_failed(item.outbox_id, now, error)
            processed += 1
        return processed


__all__ = [
    "SchedulingCheckpointNotificationSourceProjector",
    "SchedulingCheckpointOutboxItem",
]

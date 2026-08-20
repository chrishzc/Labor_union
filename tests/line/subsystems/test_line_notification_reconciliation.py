"""
File: test_line_notification_reconciliation.py
Description: 驗證通知 reconciler 僅補建遺失 decision，並將 provider 投遞交由既有冪等意圖處理。
"""

from __future__ import annotations

from datetime import datetime, timezone

from subsystems.line.notification_policy import NotificationSourceEvent
from subsystems.line.notification_reconciliation import LineNotificationReconciler


class _Repository:
    def __init__(self, events: tuple[NotificationSourceEvent, ...]) -> None:
        self._events = events
        self.projected: list[str] = []

    def list_sources_without_decisions(self, *, limit: int = 100):
        return self._events[:limit]

    def register_and_project(self, event: NotificationSourceEvent) -> int:
        self.projected.append(event.identity)
        return len(self.projected)


def _event(identity: str) -> NotificationSourceEvent:
    return NotificationSourceEvent(
        identity=identity,
        event_code="service_time_checkpoint",
        historical_silent=False,
        facts={"case_no": "C-1", "baby_log_completed": False, "requires_cooking": False},
        source_domain="scheduling",
        source_aggregate_type="case_staff_assignment",
        source_aggregate_identity="1",
        source_version=1,
        occurred_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )


def test_reconciler_projects_each_missing_decision_once_per_run() -> None:
    repository = _Repository((_event("checkpoint:1"), _event("checkpoint:2")))

    result = LineNotificationReconciler().reconcile(repository, limit=1)

    assert result == 1
    assert repository.projected == ["checkpoint:1"]


def test_reconciler_leaves_an_empty_source_set_unchanged() -> None:
    repository = _Repository(())

    assert LineNotificationReconciler().reconcile(repository) == 0
    assert repository.projected == []

"""
File: test_scheduling_rebuild_notification_invalidation.py
Description: 驗證排班替換只取消舊指派衍生的未送出服務日日誌提醒，失敗走既定重試。
"""

from datetime import datetime, timezone

from subsystems.line.scheduling_rebuild_notification_invalidation import (
    SchedulingRebuildNotificationInvalidationProjector,
    SchedulingRebuildOutboxItem,
)


class _Outbox:
    def __init__(self) -> None:
        self.published: list[int] = []
        self.failed: list[int] = []

    def claim_due(self, _now, _limit):
        return (SchedulingRebuildOutboxItem(5, (12, 13)),)

    def mark_published(self, outbox_id: int) -> None:
        self.published.append(outbox_id)

    def mark_retry_or_failed(self, outbox_id: int, _now, _error: Exception) -> None:
        self.failed.append(outbox_id)


class _Notifications:
    def __init__(self, *, fail: bool = False) -> None:
        self.assignment_ids: list[tuple[int, ...]] = []
        self._fail = fail

    def cancel_service_day_log_reminders_for_assignments(
        self, assignment_ids: tuple[int, ...]
    ) -> int:
        self.assignment_ids.append(assignment_ids)
        if self._fail:
            raise RuntimeError("unexpected_projection_failure")
        return 2


def test_rebuild_cancels_only_explicitly_replaced_assignment_reminders() -> None:
    outbox = _Outbox()
    notifications = _Notifications()

    processed = SchedulingRebuildNotificationInvalidationProjector(
        outbox, notifications
    ).run_once(datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert processed == 1
    assert notifications.assignment_ids == [(12, 13)]
    assert outbox.published == [5]
    assert outbox.failed == []


def test_rebuild_projection_failure_is_left_for_bounded_retry_policy() -> None:
    outbox = _Outbox()
    notifications = _Notifications(fail=True)

    processed = SchedulingRebuildNotificationInvalidationProjector(
        outbox, notifications
    ).run_once(datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert processed == 1
    assert outbox.published == []
    assert outbox.failed == [5]

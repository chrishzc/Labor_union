"""
File: test_service_day_log_notification_stop.py
Description: 驗證日誌完成只停止同一指派與服務日尚未送出的提醒，失敗則保留 owner outbox 重試。
"""

from datetime import UTC, datetime

from subsystems.line.service_day_log_notification_stop import (
    ServiceDayLogNotificationStopProjector,
    ServiceDayLogOutboxItem,
)


def test_completed_log_cancels_exact_service_day_reminders_then_publishes_outbox() -> None:
    recorded: list[object] = []

    class Outbox:
        def claim_due(self, _now, _limit):
            return (ServiceDayLogOutboxItem(17, 8, "2026-08-16"),)

        def mark_published(self, outbox_id):
            recorded.append(("published", outbox_id))

        def mark_retry_or_failed(self, *_args):
            raise AssertionError("valid cancellation cannot retry")

    class Notifications:
        def cancel_service_day_log_reminders(self, assignment_id, service_date):
            recorded.append(("cancel", assignment_id, service_date))
            return 2

    result = ServiceDayLogNotificationStopProjector(Outbox(), Notifications()).run_once(
        datetime(2026, 8, 16, 11, tzinfo=UTC)
    )

    assert result == 1
    assert recorded == [("cancel", 8, "2026-08-16"), ("published", 17)]


def test_cancellation_failure_keeps_outbox_for_bounded_retry() -> None:
    recorded: list[str] = []

    class Outbox:
        def claim_due(self, _now, _limit):
            return (ServiceDayLogOutboxItem(17, 8, "2026-08-16"),)

        def mark_published(self, _outbox_id):
            raise AssertionError("failed cancellation cannot publish")

        def mark_retry_or_failed(self, _outbox_id, _now, error):
            recorded.append(type(error).__name__)

    class Notifications:
        def cancel_service_day_log_reminders(self, _assignment_id, _service_date):
            raise RuntimeError("temporary database failure")

    ServiceDayLogNotificationStopProjector(Outbox(), Notifications()).run_once(
        datetime(2026, 8, 16, 11, tzinfo=UTC)
    )

    assert recorded == ["RuntimeError"]

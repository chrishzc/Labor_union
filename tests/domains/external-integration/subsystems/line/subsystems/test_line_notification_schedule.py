"""
File: test_line_notification_schedule.py
Description: 驗證通知規則以服務結束為基準，並可受控地排定一次或每日重複提醒。
"""

from datetime import UTC, datetime

from subsystems.line.notification_schedule import schedule_notification_occurrences


def test_service_end_daily_frequency_is_calculated_from_actual_checkpoint() -> None:
    occurrences = schedule_notification_occurrences(
        occurred_at=datetime(2026, 8, 16, 10, 30, tzinfo=UTC),
        schedule={"kind": "service_end"},
        frequency={"kind": "recurring_bounded", "maximum_occurrences": 3, "interval_days": 1},
    )
    assert [(item.number, item.scheduled_at.isoformat()) for item in occurrences] == [
        (1, "2026-08-16T10:30:00+00:00"),
        (2, "2026-08-17T10:30:00+00:00"),
        (3, "2026-08-18T10:30:00+00:00"),
    ]

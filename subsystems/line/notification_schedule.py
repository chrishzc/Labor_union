"""
File: notification_schedule.py
Description: 依已白名單的通知規則，計算不可變來源事件的單次或每日重複提醒時點。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping


@dataclass(frozen=True, slots=True)
class NotificationOccurrence:
    number: int
    scheduled_at: datetime


def schedule_notification_occurrences(
    *,
    occurred_at: datetime,
    schedule: Mapping[str, object],
    frequency: Mapping[str, object],
) -> tuple[NotificationOccurrence, ...]:
    """Return bounded due times; validation is owned by notification-rule grammar."""
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("notification source time must be timezone-aware")
    kind = schedule.get("kind")
    if kind in {"immediate", "service_end"}:
        first_due = occurred_at
    elif kind == "relative_service_time":
        offset = schedule.get("offset_seconds")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("notification schedule offset is invalid")
        first_due = occurred_at + timedelta(seconds=offset)
    else:
        raise ValueError("notification schedule kind is invalid")

    if frequency.get("kind", "once") == "once":
        return (NotificationOccurrence(1, first_due),)
    maximum = frequency.get("maximum_occurrences")
    interval_days = frequency.get("interval_days")
    if (
        not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or maximum < 1
        or not isinstance(interval_days, int)
        or isinstance(interval_days, bool)
        or interval_days < 1
    ):
        raise ValueError("recurring notification frequency is invalid")
    return tuple(
        NotificationOccurrence(number, first_due + timedelta(days=interval_days * (number - 1)))
        for number in range(1, maximum + 1)
    )


__all__ = ["NotificationOccurrence", "schedule_notification_occurrences"]

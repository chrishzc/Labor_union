"""Provide the Taipei business instant from an aware UTC instant."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_TAIPEI = ZoneInfo("Asia/Taipei")


def current_business_instant(utc_now: datetime | None = None) -> datetime:
    instant = datetime.now(timezone.utc) if utc_now is None else utc_now
    if not isinstance(instant, datetime):
        raise TypeError("utc_now must be an aware UTC datetime or None")
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("utc_now must be timezone-aware")
    if instant.utcoffset().total_seconds() != 0:
        raise ValueError("utc_now must use a UTC offset")
    return instant.astimezone(_TAIPEI)


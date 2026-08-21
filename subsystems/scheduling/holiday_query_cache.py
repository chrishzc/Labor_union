"""
File: holiday_query_cache.py
Description: 快取 immutable 國定假日 horizon projection，且只在 commit 後由外層失效。
"""

from __future__ import annotations

from datetime import date
from threading import RLock

from shared_kernel.ttl_cache import TtlProjectionCache
from subsystems.scheduling.holiday_calendar_query import (
    HolidayCalendarFacts,
    SchedulingHolidayQuery,
)

_holiday_cache = TtlProjectionCache[HolidayCalendarFacts](ttl_seconds=30)
_key_lock = RLock()
_known_keys: set[str] = set()


def query_holidays(
    query: SchedulingHolidayQuery,
    from_date: date,
    to_date: date,
) -> HolidayCalendarFacts:
    key = f"holiday-management:{from_date.isoformat()}:{to_date.isoformat()}"
    with _key_lock:
        _known_keys.add(key)
    return _holiday_cache.get_or_load(
        key,
        lambda: query.query(from_date, to_date, lock=False),
    )


def invalidate_holiday_query_cache() -> None:
    with _key_lock:
        keys = tuple(_known_keys)
        _known_keys.clear()
    for key in keys:
        _holiday_cache.invalidate(key)


def holiday_query_cache_telemetry():
    return _holiday_cache.telemetry()

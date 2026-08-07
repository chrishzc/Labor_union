"""Cache the read-only holiday projection for the scheduling UI."""

from __future__ import annotations

from infrastructure.mysql import mysql_adapter
from shared_kernel.ttl_cache import TtlProjectionCache

_HOLIDAY_CACHE_KEY = "holiday-management-list"
_holiday_cache = TtlProjectionCache(ttl_seconds=30)


def query_holidays() -> list[dict]:
    return _holiday_cache.get_or_load(
        _HOLIDAY_CACHE_KEY,
        lambda: mysql_adapter.get_table_data("holidays"),
    )


def invalidate_holiday_query_cache() -> None:
    _holiday_cache.invalidate(_HOLIDAY_CACHE_KEY)


def holiday_query_cache_telemetry():
    return _holiday_cache.telemetry()

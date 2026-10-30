"""
File: holiday_query_cache.py
Description: 快取 immutable 國定假日唯讀投影並支援選用外部快取後端，僅於儲存成功後失效。
"""

from __future__ import annotations

from datetime import date
import json
from typing import Callable

from shared_kernel.performance import CacheKeyParts, build_cache_key
from shared_kernel.ttl_cache import ExternalCacheBackend, TtlProjectionCache
from subsystems.scheduling.holiday_calendar_query import (
    HolidayCalendarFacts,
    HolidayFact,
    SchedulingHolidayQuery,
)


def _serialize_calendar(facts: HolidayCalendarFacts) -> str:
    return json.dumps(
        {
            "source_identity": facts.source_identity,
            "holiday_version": facts.holiday_version,
            "holidays": [
                {
                    "holiday_date": item.holiday_date.isoformat(),
                    "holiday_name": item.holiday_name,
                    "is_double_pay_default": bool(item.is_double_pay_default),
                }
                for item in facts.holidays
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _deserialize_calendar(raw: str) -> HolidayCalendarFacts:
    payload = json.loads(raw)
    return HolidayCalendarFacts(
        source_identity=str(payload["source_identity"]),
        holiday_version=str(payload["holiday_version"]),
        holidays=tuple(
            HolidayFact(
                holiday_date=date.fromisoformat(str(item["holiday_date"])),
                holiday_name=str(item["holiday_name"]),
                is_double_pay_default=bool(item.get("is_double_pay_default", False)),
            )
            for item in payload["holidays"]
        ),
    )


_HOLIDAY_KEY_PREFIX = "scheduling.holidays:"
_holiday_cache = TtlProjectionCache[HolidayCalendarFacts](
    ttl_seconds=30,
    serialize=_serialize_calendar,
    deserialize=_deserialize_calendar,
)


def configure_holiday_query_cache_backend(
    backend_provider: Callable[[], ExternalCacheBackend | None] | None,
) -> None:
    _holiday_cache.configure_backend(
        backend_provider,
        serialize=_serialize_calendar,
        deserialize=_deserialize_calendar,
    )


def _holiday_cache_key(from_date: date, to_date: date) -> str:
    digest = build_cache_key(
        CacheKeyParts(
            namespace="scheduling.holidays",
            resource_identity=f"{from_date.isoformat()}:{to_date.isoformat()}",
            permission_scope=("admin",),
            facts_version=0,
            contract_version="v1",
            time_zone="Asia/Taipei",
        )
    )
    return f"{_HOLIDAY_KEY_PREFIX}{digest}"


def query_holidays(
    query: SchedulingHolidayQuery,
    from_date: date,
    to_date: date,
) -> HolidayCalendarFacts:
    key = _holiday_cache_key(from_date, to_date)
    return _holiday_cache.get_or_load(
        key,
        lambda: query.query(from_date, to_date, lock=False),
    )


def invalidate_holiday_query_cache() -> None:
    _holiday_cache.invalidate_prefix(_HOLIDAY_KEY_PREFIX)


def holiday_query_cache_telemetry():
    return _holiday_cache.telemetry()

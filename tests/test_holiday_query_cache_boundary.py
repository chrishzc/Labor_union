"""
File: test_holiday_query_cache_boundary.py
Description: 驗證 Holiday read projection cache 不洩漏 mutable 或失效的 horizon facts。
"""

from __future__ import annotations

from datetime import date

from subsystems.scheduling import holiday_query_cache
from subsystems.scheduling.holiday_calendar_query import HolidayCalendarFacts, HolidayFact


class _Query:
    def __init__(self) -> None:
        self.loads = 0
        self.value = HolidayCalendarFacts(
            "fake:holidays/v1",
            "a" * 64,
            (HolidayFact(date(2026, 8, 8), "父親節", False),),
        )

    def query(self, _from_date, _to_date, *, lock):
        assert lock is False
        self.loads += 1
        return self.value


def test_holiday_query_cache_hits_then_invalidates_horizon_projection():
    query = _Query()
    start = date(2026, 8, 1)
    end = date(2026, 8, 31)
    holiday_query_cache.invalidate_holiday_query_cache()
    before = holiday_query_cache.holiday_query_cache_telemetry()

    first = holiday_query_cache.query_holidays(query, start, end)
    second = holiday_query_cache.query_holidays(query, start, end)
    holiday_query_cache.invalidate_holiday_query_cache()
    third = holiday_query_cache.query_holidays(query, start, end)
    after = holiday_query_cache.holiday_query_cache_telemetry()

    assert first == second == third == query.value
    assert query.loads == 2
    assert after.miss_count - before.miss_count == 2
    assert after.hit_count - before.hit_count == 1
    assert after.load_count - before.load_count == 2
    assert after.invalidation_count - before.invalidation_count == 1

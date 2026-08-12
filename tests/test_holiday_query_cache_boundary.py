"""Read-projection cache behavior must not leak mutable or stale holiday data."""

from __future__ import annotations

from subsystems.scheduling import holiday_query_cache


def test_holiday_query_cache_hits_then_invalidates_without_exposing_cached_mutation(
    monkeypatch,
):
    loads: list[int] = []
    source_value = [{"holiday_date": "2026-08-08", "name": "父親節"}]
    monkeypatch.setattr(
        holiday_query_cache.mysql_adapter,
        "get_table_data",
        lambda _table: _load_source(loads, source_value),
    )
    holiday_query_cache.invalidate_holiday_query_cache()
    before = holiday_query_cache.holiday_query_cache_telemetry()

    first = holiday_query_cache.query_holidays()
    first[0]["name"] = "mutated by caller"
    second = holiday_query_cache.query_holidays()
    holiday_query_cache.invalidate_holiday_query_cache()
    third = holiday_query_cache.query_holidays()
    after = holiday_query_cache.holiday_query_cache_telemetry()

    assert second == source_value
    assert third == source_value
    assert loads == [1, 2]
    assert after.miss_count - before.miss_count == 2
    assert after.hit_count - before.hit_count == 1
    assert after.load_count - before.load_count == 2
    assert after.invalidation_count - before.invalidation_count == 1


def _load_source(loads: list[int], source_value: list[dict[str, str]]) -> list[dict[str, str]]:
    loads.append(len(loads) + 1)
    return source_value

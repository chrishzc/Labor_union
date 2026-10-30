"""
File: test_redis_projection_cache.py
Description: 驗證 TTL 唯讀投影快取之雙層命中、單飛防擊穿、Redis 斷線冷卻降級與跨程序失效契約。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import fnmatch
import json
from threading import Barrier

from infrastructure.cache.redis_projection_cache import RedisCacheBackend
from shared_kernel.ttl_cache import TtlProjectionCache


class _FakeRedisClient:
    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int]] = {}
        self.fail_error: Exception | None = None
        self.closed = 0

    def get(self, key: str) -> str | None:
        if self.fail_error is not None:
            raise self.fail_error
        entry = self.store.get(key)
        return None if entry is None else entry[0]

    def set(self, key: str, payload: str, *, ex: int) -> None:
        if self.fail_error is not None:
            raise self.fail_error
        self.store[key] = (payload, ex)

    def delete(self, *keys: str) -> int:
        if self.fail_error is not None:
            raise self.fail_error
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                removed += 1
        return removed

    def scan_iter(self, *, match: str = "*", count: int = 100):
        del count
        if self.fail_error is not None:
            raise self.fail_error
        for key in list(self.store):
            if fnmatch.fnmatchcase(key, match):
                yield key

    def close(self) -> None:
        self.closed += 1


def _new_cache(backend: RedisCacheBackend) -> TtlProjectionCache[dict[str, object]]:
    return TtlProjectionCache(
        ttl_seconds=30,
        serialize=lambda data: json.dumps(data, ensure_ascii=False),
        deserialize=json.loads,
        backend_provider=lambda: backend,
    )


def test_l2_redis_populates_other_worker_l1_and_prefix_invalidation_clears_cross_process_entries():
    redis_client = _FakeRedisClient()
    backend = RedisCacheBackend(
        "redis://127.0.0.1:6379/0",
        client_factory=lambda _url, _timeout: redis_client,
    )
    worker_a = _new_cache(backend)
    worker_b = _new_cache(backend)
    loads = 0

    def loader() -> dict[str, object]:
        nonlocal loads
        loads += 1
        return {"version": loads, "items": ["國慶日"]}

    first = worker_a.get_or_load("scheduling.holidays:2026", loader)
    # Worker B has an empty L1 memory cache, so it should hydrate from L2 Redis without calling loader()
    second = worker_b.get_or_load("scheduling.holidays:2026", loader)
    assert first == second == {"version": 1, "items": ["國慶日"]}
    assert loads == 1
    assert "labor-union:query-cache:v1:scheduling.holidays:2026" in redis_client.store

    # Worker C (fresh process that never read into L1) performs post-commit prefix invalidation
    worker_c = _new_cache(backend)
    worker_c.invalidate_prefix("scheduling.holidays:")
    assert redis_client.store == {}

    worker_a.invalidate_prefix("scheduling.holidays:")
    refreshed = worker_a.get_or_load("scheduling.holidays:2026", loader)
    assert refreshed == {"version": 2, "items": ["國慶日"]}
    assert loads == 2


def test_redis_error_trips_cooldown_without_blocking_read_and_recovers_after_cooldown():
    now = [50.0]
    factory_calls = 0
    current_client = _FakeRedisClient()

    def factory(_url: str, _timeout: float) -> _FakeRedisClient:
        nonlocal factory_calls
        factory_calls += 1
        return current_client

    backend = RedisCacheBackend(
        "redis://127.0.0.1:6379/0",
        failure_cooldown_seconds=5.0,
        clock=lambda: now[0],
        client_factory=factory,
    )
    cache = _new_cache(backend)
    current_client.fail_error = TimeoutError("redis socket timeout")

    loads = 0

    def loader() -> dict[str, object]:
        nonlocal loads
        loads += 1
        return {"revision": loads}

    # First miss attempts Redis, trips 5-second cooldown, and still succeeds via loader + L1
    assert cache.get_or_load("pricing:catalog", loader) == {"revision": 1}
    assert factory_calls == 1
    assert current_client.closed == 1

    # During cooldown window, another key miss skips Redis client creation completely
    now[0] += 2.0
    assert cache.get_or_load("pricing:other", loader) == {"revision": 2}
    assert factory_calls == 1

    # After 5s cooldown elapses, healthy Redis reconnects and stores payload
    current_client = _FakeRedisClient()
    now[0] += 4.0
    assert cache.get_or_load("pricing:recovered", loader) == {"revision": 3}
    assert factory_calls == 2
    assert "labor-union:query-cache:v1:pricing:recovered" in current_client.store


def test_single_flight_coalesces_concurrent_misses_for_same_key():
    barrier = Barrier(4)
    loads = 0

    cache = TtlProjectionCache[dict[str, int]](ttl_seconds=30)

    def slow_loader() -> dict[str, int]:
        nonlocal loads
        loads += 1
        return {"count": loads}

    def worker(_index: int) -> dict[str, int]:
        barrier.wait(timeout=5)
        return cache.get_or_load("coalesced:key", slow_loader)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, range(4)))

    assert loads == 1
    assert results == [{"count": 1}] * 4
    telemetry = cache.telemetry()
    assert telemetry.load_count == 1
    assert telemetry.hit_count == 3

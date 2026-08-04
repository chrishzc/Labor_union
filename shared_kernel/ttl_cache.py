"""Small thread-safe TTL cache for non-authoritative read projections."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


@dataclass(frozen=True, slots=True)
class CacheTelemetry:
    hit_count: int
    miss_count: int
    load_count: int
    invalidation_count: int


class TtlProjectionCache(Generic[T]):
    def __init__(self, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl_seconds = float(ttl_seconds)
        self._entries: dict[str, _CacheEntry[T]] = {}
        self._lock = RLock()
        self._hit_count = 0
        self._miss_count = 0
        self._load_count = 0
        self._invalidation_count = 0

    def get_or_load(self, key: str, loader: Callable[[], T]) -> T:
        if not key.strip():
            raise ValueError("cache key is required")
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at > monotonic():
                self._hit_count += 1
                return deepcopy(entry.value)
            self._miss_count += 1
            value = loader()
            self._load_count += 1
            self._entries[key] = _CacheEntry(
                deepcopy(value),
                monotonic() + self._ttl_seconds,
            )
            return deepcopy(value)

    def invalidate(self, key: str) -> None:
        with self._lock:
            if self._entries.pop(key, None) is not None:
                self._invalidation_count += 1

    def telemetry(self) -> CacheTelemetry:
        with self._lock:
            return CacheTelemetry(
                self._hit_count,
                self._miss_count,
                self._load_count,
                self._invalidation_count,
            )


__all__ = ["CacheTelemetry", "TtlProjectionCache"]

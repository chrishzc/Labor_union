"""
File: ttl_cache.py
Description: 提供執行緒安全 TTL 唯讀投影快取、單飛防擊穿與選用外部快取後端介面。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable, Generic, Protocol, TypeVar

T = TypeVar("T")


class ExternalCacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, payload: str, ttl_seconds: float) -> None: ...

    def delete(self, keys: tuple[str, ...]) -> None: ...

    def delete_prefix(self, prefix: str) -> None: ...


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
    def __init__(
        self,
        ttl_seconds: float,
        *,
        serialize: Callable[[T], str] | None = None,
        deserialize: Callable[[str], T] | None = None,
        backend_provider: Callable[[], ExternalCacheBackend | None] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl_seconds = float(ttl_seconds)
        self._entries: dict[str, _CacheEntry[T]] = {}
        self._lock = RLock()
        self._key_locks: dict[str, RLock] = {}
        self._serialize = serialize
        self._deserialize = deserialize
        self._backend_provider = backend_provider
        self._hit_count = 0
        self._miss_count = 0
        self._load_count = 0
        self._invalidation_count = 0

    def configure_backend(
        self,
        backend_provider: Callable[[], ExternalCacheBackend | None] | None,
        *,
        serialize: Callable[[T], str] | None = None,
        deserialize: Callable[[str], T] | None = None,
    ) -> None:
        with self._lock:
            self._backend_provider = backend_provider
            if serialize is not None:
                self._serialize = serialize
            if deserialize is not None:
                self._deserialize = deserialize

    def _resolve_backend(
        self,
    ) -> tuple[ExternalCacheBackend | None, Callable[[T], str] | None, Callable[[str], T] | None]:
        with self._lock:
            provider = self._backend_provider
            serialize = self._serialize
            deserialize = self._deserialize
        if provider is None or serialize is None or deserialize is None:
            return None, None, None
        try:
            return provider(), serialize, deserialize
        except Exception:
            return None, None, None

    def _acquire_key_lock(self, key: str) -> RLock:
        with self._lock:
            key_lock = self._key_locks.get(key)
            if key_lock is None:
                key_lock = RLock()
                self._key_locks[key] = key_lock
            return key_lock

    def get_or_load(self, key: str, loader: Callable[[], T]) -> T:
        if not key.strip():
            raise ValueError("cache key is required")
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at > monotonic():
                self._hit_count += 1
                return deepcopy(entry.value)

        key_lock = self._acquire_key_lock(key)
        with key_lock:
            with self._lock:
                entry = self._entries.get(key)
                if entry is not None and entry.expires_at > monotonic():
                    self._hit_count += 1
                    return deepcopy(entry.value)

            backend, serialize, deserialize = self._resolve_backend()
            if backend is not None and deserialize is not None:
                try:
                    raw = backend.get(key)
                    if raw is not None:
                        decoded = deserialize(raw)
                        with self._lock:
                            self._entries[key] = _CacheEntry(
                                deepcopy(decoded),
                                monotonic() + self._ttl_seconds,
                            )
                            self._hit_count += 1
                        return deepcopy(decoded)
                except Exception:
                    pass

            with self._lock:
                self._miss_count += 1
            value = loader()
            with self._lock:
                self._load_count += 1
                self._entries[key] = _CacheEntry(
                    deepcopy(value),
                    monotonic() + self._ttl_seconds,
                )
            if backend is not None and serialize is not None:
                try:
                    backend.set(key, serialize(value), self._ttl_seconds)
                except Exception:
                    pass
            return deepcopy(value)

    def invalidate(self, key: str) -> None:
        self.invalidate_many((key,))

    def invalidate_many(self, keys: tuple[str, ...]) -> None:
        cleaned = tuple(key for key in keys if key.strip())
        if not cleaned:
            return
        with self._lock:
            for key in cleaned:
                if self._entries.pop(key, None) is not None:
                    self._invalidation_count += 1
        backend, _serialize, _deserialize = self._resolve_backend()
        if backend is not None:
            try:
                backend.delete(cleaned)
            except Exception:
                pass

    def invalidate_prefix(self, prefix: str) -> None:
        cleaned = prefix.strip()
        if not cleaned:
            return
        with self._lock:
            matched = [key for key in self._entries if key.startswith(cleaned)]
            for key in matched:
                if self._entries.pop(key, None) is not None:
                    self._invalidation_count += 1
        backend, _serialize, _deserialize = self._resolve_backend()
        if backend is not None and hasattr(backend, "delete_prefix"):
            try:
                backend.delete_prefix(cleaned)
            except Exception:
                pass

    def telemetry(self) -> CacheTelemetry:
        with self._lock:
            return CacheTelemetry(
                self._hit_count,
                self._miss_count,
                self._load_count,
                self._invalidation_count,
            )


__all__ = ["CacheTelemetry", "ExternalCacheBackend", "TtlProjectionCache"]

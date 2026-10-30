"""
File: redis_projection_cache.py
Description: 以本機 Redis 加速唯讀投影快取，異常或未啟用時無副作用退回記憶體快取。
"""

from __future__ import annotations

import math
import os
from threading import Lock
from time import monotonic
from typing import Any, Callable

_KEY_PREFIX = "labor-union:query-cache:v1:"
_DEFAULT_SOCKET_TIMEOUT_SECONDS = 0.15
_DEFAULT_FAILURE_COOLDOWN_SECONDS = 5.0


class RedisCacheBackend:
    """Bounded read-only projection cache backend with fast failure cooldown."""

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str = _KEY_PREFIX,
        socket_timeout_seconds: float = _DEFAULT_SOCKET_TIMEOUT_SECONDS,
        failure_cooldown_seconds: float = _DEFAULT_FAILURE_COOLDOWN_SECONDS,
        clock: Callable[[], float] = monotonic,
        client_factory: Callable[[str, float], Any] | None = None,
    ) -> None:
        cleaned_url = redis_url.strip()
        if not cleaned_url:
            raise ValueError("redis_url must not be empty")
        self._redis_url = cleaned_url
        self._key_prefix = key_prefix
        self._socket_timeout = max(0.05, float(socket_timeout_seconds))
        self._cooldown_seconds = max(0.0, float(failure_cooldown_seconds))
        self._clock = clock
        self._client_factory = client_factory or _build_redis_client
        self._lock = Lock()
        self._client: Any | None = None
        self._retry_after: float = 0.0

    def _prefixed(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    def _acquire_client(self) -> Any | None:
        now = self._clock()
        with self._lock:
            if now < self._retry_after:
                return None
            if self._client is not None:
                return self._client
        try:
            created = self._client_factory(self._redis_url, self._socket_timeout)
        except Exception:
            self._trip_cooldown()
            return None
        with self._lock:
            if self._client is None:
                self._client = created
            return self._client

    def _trip_cooldown(self) -> None:
        now = self._clock()
        old_client = None
        with self._lock:
            self._retry_after = now + self._cooldown_seconds
            old_client = self._client
            self._client = None
        if old_client is not None and hasattr(old_client, "close"):
            try:
                old_client.close()
            except Exception:
                pass

    def get(self, key: str) -> str | None:
        client = self._acquire_client()
        if client is None:
            return None
        try:
            value = client.get(self._prefixed(key))
        except Exception:
            self._trip_cooldown()
            return None
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    def set(self, key: str, payload: str, ttl_seconds: float) -> None:
        client = self._acquire_client()
        if client is None:
            return
        ttl = max(1, int(math.ceil(ttl_seconds)))
        try:
            client.set(self._prefixed(key), payload, ex=ttl)
        except Exception:
            self._trip_cooldown()

    def delete(self, keys: tuple[str, ...]) -> None:
        if not keys:
            return
        client = self._acquire_client()
        if client is None:
            return
        prefixed_keys = [self._prefixed(key) for key in keys if key.strip()]
        if not prefixed_keys:
            return
        try:
            client.delete(*prefixed_keys)
        except Exception:
            self._trip_cooldown()

    def delete_prefix(self, prefix: str) -> None:
        cleaned = prefix.strip()
        if not cleaned:
            return
        client = self._acquire_client()
        if client is None:
            return
        pattern = f"{self._prefixed(cleaned)}*"
        try:
            matched = tuple(client.scan_iter(match=pattern, count=100))
            if matched:
                client.delete(*matched)
        except Exception:
            self._trip_cooldown()

    def close(self) -> None:
        with self._lock:
            client = self._client
            self._client = None
        if client is not None and hasattr(client, "close"):
            try:
                client.close()
            except Exception:
                pass


def _build_redis_client(redis_url: str, socket_timeout_seconds: float) -> Any:
    import redis

    return redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=socket_timeout_seconds,
        socket_timeout=socket_timeout_seconds,
    )


_DEFAULT_LOCK = Lock()
_DEFAULT_URL: str = ""
_DEFAULT_BACKEND: RedisCacheBackend | None = None


def default_redis_cache_backend() -> RedisCacheBackend | None:
    """Return a shared Redis cache backend when REDIS_URL is configured, else None."""
    global _DEFAULT_URL, _DEFAULT_BACKEND
    configured_url = os.getenv("REDIS_URL", "").strip()
    with _DEFAULT_LOCK:
        if not configured_url:
            old = _DEFAULT_BACKEND
            _DEFAULT_BACKEND = None
            _DEFAULT_URL = ""
            if old is not None:
                old.close()
            return None
        if _DEFAULT_BACKEND is not None and _DEFAULT_URL == configured_url:
            return _DEFAULT_BACKEND
        old = _DEFAULT_BACKEND
        _DEFAULT_BACKEND = RedisCacheBackend(configured_url)
        _DEFAULT_URL = configured_url
    if old is not None:
        old.close()
    return _DEFAULT_BACKEND


def reset_default_redis_cache_backend() -> None:
    global _DEFAULT_URL, _DEFAULT_BACKEND
    with _DEFAULT_LOCK:
        old = _DEFAULT_BACKEND
        _DEFAULT_BACKEND = None
        _DEFAULT_URL = ""
    if old is not None:
        old.close()


__all__ = [
    "RedisCacheBackend",
    "default_redis_cache_backend",
    "reset_default_redis_cache_backend",
]

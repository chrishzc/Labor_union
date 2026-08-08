"""Redis Pub/Sub wake signal adapter; MySQL remains the durable queue."""

from __future__ import annotations

import time
from typing import Any

_DEFAULT_CHANNEL = "labor-union:line:work-available"


class RedisLineWakeupPublisher:
    def __init__(self, redis_url: str, *, channel: str = _DEFAULT_CHANNEL) -> None:
        self._client = _redis_module().Redis.from_url(redis_url, decode_responses=True)
        self._channel = channel

    def publish(self) -> None:
        self._client.publish(self._channel, "wake")


class RedisLineWakeupSubscriber:
    def __init__(self, redis_url: str, *, channel: str = _DEFAULT_CHANNEL) -> None:
        self._client = _redis_module().Redis.from_url(redis_url, decode_responses=True)
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        self._pubsub.subscribe(channel)

    def wait(self, timeout_seconds: float) -> bool:
        message = self._pubsub.get_message(timeout=max(0.0, timeout_seconds))
        return bool(message and message.get("type") == "message")

    def close(self) -> None:
        self._pubsub.close()
        self._client.close()


class NoopLineWakeupPublisher:
    def publish(self) -> None:
        return None


class SleepingLineWakeupSubscriber:
    def wait(self, timeout_seconds: float) -> bool:
        time.sleep(max(0.0, timeout_seconds))
        return False


def _redis_module() -> Any:
    try:
        import redis
    except ImportError as error:
        raise RuntimeError("redis package is required when REDIS_URL is configured") from error
    return redis


__all__ = [
    "NoopLineWakeupPublisher",
    "RedisLineWakeupPublisher",
    "RedisLineWakeupSubscriber",
    "SleepingLineWakeupSubscriber",
]

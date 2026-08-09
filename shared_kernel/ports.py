"""Infrastructure ports that preserve Global transaction and performance rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol, Self

from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
)

_AGGREGATE_TYPE_MAXIMUM_LENGTH = 100
_OUTBOX_IDENTITY_MAXIMUM_LENGTH = 191
_OUTBOX_PAYLOAD_MAXIMUM_LENGTH = 65_535


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"payload JSON contains unsupported constant {value}")


def _validate_canonical_payload_json(payload_json: str) -> None:
    parsed = json.loads(payload_json, parse_constant=_reject_json_constant)
    if not isinstance(parsed, dict):
        raise ValueError("outbox payload JSON must be an object")
    canonical = json.dumps(
        parsed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if canonical != payload_json:
        raise ValueError("outbox payload JSON must be canonical")


class UnitOfWork(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> bool | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass(frozen=True, slots=True)
class OutboxIntent:
    aggregate_type: str
    aggregate_identity: str
    intent_type: str
    payload_json: str
    idempotency_identity: str

    def __post_init__(self) -> None:
        _validate_outbox_identity(self)
        require_canonical_text(
            self.payload_json,
            "payload JSON",
            _OUTBOX_PAYLOAD_MAXIMUM_LENGTH,
        )
        _validate_canonical_payload_json(self.payload_json)


def _validate_outbox_identity(intent: OutboxIntent) -> None:
    _validate_outbox_aggregate(intent)
    require_canonical_text(
        intent.intent_type,
        "intent type",
        _OUTBOX_IDENTITY_MAXIMUM_LENGTH,
    )
    require_canonical_text(
        intent.idempotency_identity,
        "outbox idempotency identity",
        _OUTBOX_IDENTITY_MAXIMUM_LENGTH,
    )


def _validate_outbox_aggregate(intent: OutboxIntent) -> None:
    require_canonical_text(
        intent.aggregate_type,
        "aggregate type",
        _AGGREGATE_TYPE_MAXIMUM_LENGTH,
    )
    require_canonical_text(
        intent.aggregate_identity,
        "aggregate identity",
        _OUTBOX_IDENTITY_MAXIMUM_LENGTH,
    )


class OutboxWriter(Protocol):
    def append(self, intent: OutboxIntent) -> int: ...


@dataclass(frozen=True, slots=True)
class CacheEntry:
    value: bytes
    generated_at: datetime
    expires_at: datetime
    facts_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, bytes):
            raise TypeError("cache value must be bytes")
        if self.generated_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("cache timestamps must be timezone-aware")
        if self.expires_at <= self.generated_at:
            raise ValueError("cache expiry must be after generation")
        require_nonnegative_integer(self.facts_version, "cache facts version")


class QueryCachePort(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...

    def put(self, key: str, entry: CacheEntry) -> None: ...

    def invalidate(self, key: str) -> None: ...


class PerformanceTelemetryPort(Protocol):
    def record_timing(
        self,
        metric_name: str,
        duration_milliseconds: float,
        attributes: Mapping[str, str],
    ) -> None: ...

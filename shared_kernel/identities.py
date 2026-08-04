"""Command identity and concurrency value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191
_ACTOR_MAXIMUM_LENGTH = 100
_PERMISSION_NAME_MAXIMUM_LENGTH = 100


def _validate_permission_scope(permission_scope: Any) -> tuple[str, ...]:
    if not isinstance(permission_scope, tuple):
        raise TypeError("permission_scope must be a tuple")
    normalized = tuple(
        require_canonical_text(
            value,
            "permission_scope item",
            _PERMISSION_NAME_MAXIMUM_LENGTH,
        )
        for value in permission_scope
    )
    if normalized != tuple(sorted(set(normalized))):
        raise ValueError("permission_scope must be sorted and unique")
    return normalized


@dataclass(frozen=True, slots=True)
class ActorContext:
    actor_id: str
    permission_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_canonical_text(self.actor_id, "actor_id", _ACTOR_MAXIMUM_LENGTH)
        _validate_permission_scope(self.permission_scope)


@dataclass(frozen=True, slots=True)
class ExpectedVersion:
    value: int

    def __post_init__(self) -> None:
        require_nonnegative_integer(self.value, "expected version")


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    value: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.value,
            "idempotency key",
            _IDENTITY_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class CorrelationId:
    value: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.value,
            "correlation id",
            _IDENTITY_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class IdempotencyReceipt:
    key: IdempotencyKey
    payload_fingerprint: PreviewFingerprint
    result_reference: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.result_reference,
            "result reference",
            _IDENTITY_MAXIMUM_LENGTH,
        )

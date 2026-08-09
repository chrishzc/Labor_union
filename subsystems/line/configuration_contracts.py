"""Typed application contracts for versioned LINE configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from domains.line.configuration import (
    LineConfigurationCandidate,
    LineConfigurationKind,
    LineConfigurationSnapshot,
)
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text

_CONFIGURATION_REASON_MAXIMUM_LENGTH = 1_000


class LineConfigurationCommandOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class GetLineConfigurationQuery:
    kind: LineConfigurationKind


@dataclass(frozen=True, slots=True)
class PreviewLineConfigurationCommand:
    kind: LineConfigurationKind
    expected_revision: LineConfigurationRevision
    definition: Mapping[str, object]
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ApplyLineConfigurationCommand:
    candidate: LineConfigurationCandidate
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(
            self.reason,
            "LINE configuration change reason",
            _CONFIGURATION_REASON_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class ApplyLineConfigurationResult:
    outcome: LineConfigurationCommandOutcome
    snapshot: LineConfigurationSnapshot


__all__ = [
    "ApplyLineConfigurationCommand",
    "ApplyLineConfigurationResult",
    "GetLineConfigurationQuery",
    "LineConfigurationCommandOutcome",
    "PreviewLineConfigurationCommand",
]

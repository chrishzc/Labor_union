"""
File: configuration_contracts.py
Description: 定義版本化 LINE 設定命令與不暴露 definition 的安全查詢契約。
"""

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
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

_CONFIGURATION_REASON_MAXIMUM_LENGTH = 1_000


class LineConfigurationCommandOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


class LineConfigurationSafeState(StrEnum):
    EMPTY = "empty"
    CONFIGURED = "configured"


class LineConfigurationQueryContractError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("LINE configuration query contract is invalid")


class LineConfigurationQueryUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("LINE configuration query is unavailable")


@dataclass(frozen=True, slots=True)
class GetLineConfigurationQuery:
    kind: LineConfigurationKind


@dataclass(frozen=True, slots=True)
class GetLineConfigurationSafeQuery:
    kind: LineConfigurationKind

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LineConfigurationKind):
            raise TypeError("LINE configuration kind is invalid")


@dataclass(frozen=True, slots=True)
class LineConfigurationSafeResult:
    kind: LineConfigurationKind
    revision: int
    state: LineConfigurationSafeState

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LineConfigurationKind):
            raise TypeError("LINE configuration kind is invalid")
        require_nonnegative_integer(self.revision, "LINE configuration revision")
        if not isinstance(self.state, LineConfigurationSafeState):
            raise TypeError("LINE configuration safe state is invalid")


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
    "GetLineConfigurationSafeQuery",
    "LineConfigurationCommandOutcome",
    "LineConfigurationQueryContractError",
    "LineConfigurationQueryUnavailableError",
    "LineConfigurationSafeResult",
    "LineConfigurationSafeState",
    "PreviewLineConfigurationCommand",
]

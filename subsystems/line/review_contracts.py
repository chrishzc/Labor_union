"""Typed application contracts for LINE review queries and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.line.identities import LineReviewRequestId
from domains.line.review import (
    LineReviewDecision,
    LineReviewDecisionCandidate,
    LineReviewSnapshot,
    LineReviewStatus,
    LineReviewType,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.validation import require_canonical_text, require_positive_integer

_QUERY_CURSOR_MAXIMUM_LENGTH = 191
_REVIEW_REASON_MAXIMUM_LENGTH = 1_000
_MAXIMUM_REVIEW_PAGE_SIZE = 100


class LineReviewCommandOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class LineReviewListQuery:
    statuses: tuple[LineReviewStatus, ...] = ()
    review_types: tuple[LineReviewType, ...] = ()
    page_size: int = 25
    cursor: str | None = None

    def __post_init__(self) -> None:
        _validate_enum_filter(self.statuses, LineReviewStatus, "review statuses")
        _validate_enum_filter(self.review_types, LineReviewType, "review types")
        require_positive_integer(self.page_size, "LINE review page size")
        if self.page_size > _MAXIMUM_REVIEW_PAGE_SIZE:
            raise ValueError("LINE review page size exceeds maximum")
        if self.cursor is not None:
            require_canonical_text(
                self.cursor,
                "LINE review cursor",
                _QUERY_CURSOR_MAXIMUM_LENGTH,
            )


@dataclass(frozen=True, slots=True)
class DecideLineReviewCommand:
    request_id: LineReviewRequestId
    decision: LineReviewDecision
    expected_version: ExpectedVersion
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(
            self.reason,
            "LINE review reason",
            _REVIEW_REASON_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class DecideLineReviewResult:
    outcome: LineReviewCommandOutcome
    candidate: LineReviewDecisionCandidate


@dataclass(frozen=True, slots=True)
class LineReviewPage:
    items: tuple[LineReviewSnapshot, ...]
    next_cursor: str | None


def _validate_enum_filter(values: tuple[object, ...], item_type: type, name: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"LINE {name} must be a tuple")
    if any(not isinstance(value, item_type) for value in values):
        raise TypeError(f"LINE {name} contain an invalid value")
    serialized = tuple(str(value) for value in values)
    if serialized != tuple(sorted(set(serialized))):
        raise ValueError(f"LINE {name} must be sorted and unique")


__all__ = [
    "DecideLineReviewCommand",
    "DecideLineReviewResult",
    "LineReviewCommandOutcome",
    "LineReviewListQuery",
    "LineReviewPage",
]

"""Typed M2 feedback contract; no prompt or provider payload crosses this boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text


class FeedbackOutcome(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class RecordLineFeedback:
    actor_id: str
    source_response_id: str
    outcome: FeedbackOutcome
    binding_version: int
    response_revision: int
    catalog_revision: int
    rule_revision: int | None
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.actor_id, "feedback actor", 191)
        require_canonical_text(self.source_response_id, "feedback source response", 191)
        if self.binding_version < 0 or self.response_revision < 1 or self.catalog_revision < 1:
            raise ValueError("feedback versions are invalid")
        if self.rule_revision is not None and self.rule_revision < 1:
            raise ValueError("feedback rule revision must be positive")

    @property
    def command_fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload({
            "actor_id": self.actor_id,
            "source_response_id": self.source_response_id,
            "outcome": self.outcome.value,
            "binding_version": self.binding_version,
            "response_revision": self.response_revision,
            "catalog_revision": self.catalog_revision,
            "rule_revision": self.rule_revision,
        })


@dataclass(frozen=True, slots=True)
class FeedbackPreview:
    source_response_id: str
    outcome: FeedbackOutcome
    command_fingerprint: PreviewFingerprint
    apply_ready: bool = True


@dataclass(frozen=True, slots=True)
class FeedbackRoot:
    actor_id: str
    source_response_id: str
    outcome: FeedbackOutcome
    binding_version: int
    response_revision: int
    catalog_revision: int
    rule_revision: int | None
    command_fingerprint: PreviewFingerprint
    ticket_id: int | None
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class FeedbackReceipt:
    source_response_id: str
    outcome: FeedbackOutcome
    command_fingerprint: PreviewFingerprint
    ticket_id: int | None
    replayed: bool


@dataclass(frozen=True, slots=True)
class FeedbackReadback:
    root: FeedbackRoot
    receipt: FeedbackReceipt


@dataclass(frozen=True, slots=True)
class FeedbackAggregate:
    catalog_revision: int
    window_start: datetime
    window_end: datetime
    resolved_count: int
    unresolved_count: int

    @property
    def total_count(self) -> int:
        return self.resolved_count + self.unresolved_count

    @property
    def resolved_rate(self) -> float | None:
        if not self.total_count:
            return None
        return self.resolved_count / self.total_count


class LineFeedbackRepository(Protocol):
    def get(self, actor_id: str, source_response_id: str) -> FeedbackRoot | None: ...

    def append(self, root: FeedbackRoot) -> None: ...

    def aggregate(
        self, catalog_revision: int, window_start: datetime, window_end: datetime
    ) -> FeedbackAggregate: ...


__all__ = [
    "FeedbackAggregate",
    "FeedbackOutcome",
    "FeedbackPreview",
    "FeedbackReceipt",
    "FeedbackReadback",
    "FeedbackRoot",
    "LineFeedbackRepository",
    "RecordLineFeedback",
]

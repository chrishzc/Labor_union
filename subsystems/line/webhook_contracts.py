"""Typed application contracts for LINE webhook intake and consumption."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.line.identities import LineWebhookEventId
from domains.line.webhook import (
    CanonicalLineWebhookEvent,
    LineWebhookProcessingStatus,
)
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey


class LineWebhookRegistrationOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class AcceptLineWebhookEventCommand:
    event: CanonicalLineWebhookEvent
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class AcceptLineWebhookEventResult:
    outcome: LineWebhookRegistrationOutcome
    event_id: LineWebhookEventId
    status: LineWebhookProcessingStatus
    version: ExpectedVersion


@dataclass(frozen=True, slots=True)
class ConsumeLineWebhookEventCommand:
    event_id: LineWebhookEventId
    expected_version: ExpectedVersion
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ConsumeLineWebhookEventResult:
    event_id: LineWebhookEventId
    status: LineWebhookProcessingStatus
    resulting_version: ExpectedVersion


__all__ = [
    "AcceptLineWebhookEventCommand",
    "AcceptLineWebhookEventResult",
    "ConsumeLineWebhookEventCommand",
    "ConsumeLineWebhookEventResult",
    "LineWebhookRegistrationOutcome",
]

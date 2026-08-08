"""Pure LINE webhook identity, normalization, and state rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping

from domains.line.canonical_payload import (
    canonical_line_payload_json,
    validate_canonical_line_payload_json,
)
from domains.line.identities import (
    LineDestinationId,
    LineSourceIdentity,
    LineWebhookEventId,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ExpectedVersion
from shared_kernel.validation import require_canonical_text

_EVENT_TYPE_MAXIMUM_LENGTH = 100


class LineWebhookProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"


_ALLOWED_WEBHOOK_TRANSITIONS = {
    LineWebhookProcessingStatus.PENDING: {LineWebhookProcessingStatus.PROCESSING},
    LineWebhookProcessingStatus.PROCESSING: {
        LineWebhookProcessingStatus.PROCESSED,
        LineWebhookProcessingStatus.RETRYABLE_FAILED,
        LineWebhookProcessingStatus.TERMINAL_FAILED,
    },
    LineWebhookProcessingStatus.RETRYABLE_FAILED: {
        LineWebhookProcessingStatus.PENDING,
    },
}


class LineWebhookTransitionError(ValueError):
    """Raised when a webhook inbox event attempts an invalid transition."""


@dataclass(frozen=True, slots=True)
class CanonicalLineWebhookEvent:
    event_id: LineWebhookEventId
    destination_id: LineDestinationId
    event_type: str
    source: LineSourceIdentity
    occurred_at: datetime
    payload_fingerprint: PreviewFingerprint
    is_redelivery: bool = False
    uses_provider_event_id: bool = True
    payload_json: str = "{}"

    def __post_init__(self) -> None:
        require_canonical_text(
            self.event_type,
            "LINE webhook event type",
            _EVENT_TYPE_MAXIMUM_LENGTH,
        )
        _require_aware_datetime(self.occurred_at, "webhook occurred_at")
        if not isinstance(self.is_redelivery, bool):
            raise TypeError("LINE webhook redelivery flag must be bool")
        validate_canonical_line_payload_json(self.payload_json)


@dataclass(frozen=True, slots=True)
class LineWebhookInboxSnapshot:
    event: CanonicalLineWebhookEvent
    status: LineWebhookProcessingStatus
    version: ExpectedVersion

    def __post_init__(self) -> None:
        if not isinstance(self.status, LineWebhookProcessingStatus):
            raise TypeError("LINE webhook inbox status is invalid")


# Kept cohesive so the payload fingerprint and canonical event ID cannot drift.
def build_line_webhook_event(
    *,
    provider_event_id: str | None,
    destination_id: LineDestinationId,
    event_type: str,
    source: LineSourceIdentity,
    occurred_at: datetime,
    canonical_payload: Mapping[str, object],
    is_redelivery: bool = False,
) -> CanonicalLineWebhookEvent:
    payload_json = canonical_line_payload_json(canonical_payload)
    payload_fingerprint = fingerprint_payload(canonical_payload)
    event_id, uses_provider_id = _event_identity(
        provider_event_id,
        destination_id,
        event_type,
        source,
        occurred_at,
        payload_fingerprint,
    )
    return CanonicalLineWebhookEvent(
        event_id,
        destination_id,
        event_type,
        source,
        occurred_at,
        payload_fingerprint,
        is_redelivery,
        uses_provider_id,
        payload_json,
    )


def transition_webhook_status(
    current: LineWebhookProcessingStatus,
    target: LineWebhookProcessingStatus,
) -> LineWebhookProcessingStatus:
    if not isinstance(current, LineWebhookProcessingStatus):
        raise TypeError("current webhook status is invalid")
    if target not in _ALLOWED_WEBHOOK_TRANSITIONS.get(current, set()):
        raise LineWebhookTransitionError(
            f"cannot transition LINE webhook from {current.value} to {target.value}"
        )
    return target


def _event_identity(
    provider_event_id: str | None,
    destination_id: LineDestinationId,
    event_type: str,
    source: LineSourceIdentity,
    occurred_at: datetime,
    payload_fingerprint: PreviewFingerprint,
) -> tuple[LineWebhookEventId, bool]:
    if provider_event_id is not None:
        return LineWebhookEventId(provider_event_id), True
    fallback = _fallback_identity_fingerprint(
        destination_id,
        event_type,
        source,
        occurred_at,
        payload_fingerprint,
    )
    return LineWebhookEventId(f"fingerprint:{fallback.value}"), False


# Kept cohesive because every fallback-identity fact must enter one fingerprint.
def _fallback_identity_fingerprint(
    destination_id: LineDestinationId,
    event_type: str,
    source: LineSourceIdentity,
    occurred_at: datetime,
    payload_fingerprint: PreviewFingerprint,
) -> PreviewFingerprint:
    _require_aware_datetime(occurred_at, "webhook occurred_at")
    require_canonical_text(
        event_type,
        "LINE webhook event type",
        _EVENT_TYPE_MAXIMUM_LENGTH,
    )
    return fingerprint_payload(
        {
            "destination_id": destination_id.value,
            "event_type": event_type,
            "source_type": source.source_type.value,
            "source_id": source.source_id,
            "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
            "payload_fingerprint": payload_fingerprint.value,
        }
    )


def _require_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() is None:
        raise ValueError(f"{field_name} must have a UTC offset")
    return value


__all__ = [
    "CanonicalLineWebhookEvent",
    "LineWebhookProcessingStatus",
    "LineWebhookInboxSnapshot",
    "LineWebhookTransitionError",
    "build_line_webhook_event",
    "transition_webhook_status",
]

"""Module tests for LINE webhook identities and transitions."""

from datetime import datetime, timezone

import pytest

from domains.line.identities import (
    LineDestinationId,
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
)
from domains.line.webhook import (
    LineWebhookProcessingStatus,
    LineWebhookTransitionError,
    build_line_webhook_event,
    transition_webhook_status,
)


def _user_source() -> LineSourceIdentity:
    return LineSourceIdentity(
        LineSourceType.USER,
        "U-user-1",
        LineUserId("U-user-1"),
    )


def _event(provider_event_id: str | None, payload: dict[str, object]):
    return build_line_webhook_event(
        provider_event_id=provider_event_id,
        destination_id=LineDestinationId("destination-1"),
        event_type="message",
        source=_user_source(),
        occurred_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        canonical_payload=payload,
    )


def test_provider_event_identity_is_preserved() -> None:
    event = _event("provider-event-1", {"type": "message"})

    assert event.event_id.value == "provider-event-1"
    assert event.uses_provider_event_id is True


def test_missing_provider_identity_uses_deterministic_fingerprint() -> None:
    first = _event(None, {"type": "message", "value": 1})
    replay = _event(None, {"value": 1, "type": "message"})

    assert first.event_id == replay.event_id
    assert first.event_id.value.startswith("fingerprint:")
    assert first.uses_provider_event_id is False


def test_fallback_identity_changes_with_payload() -> None:
    first = _event(None, {"value": 1})
    changed = _event(None, {"value": 2})

    assert first.event_id != changed.event_id


def test_webhook_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_line_webhook_event(
            provider_event_id=None,
            destination_id=LineDestinationId("destination-1"),
            event_type="message",
            source=_user_source(),
            occurred_at=datetime(2026, 8, 6),
            canonical_payload={"value": 1},
        )


def test_webhook_status_rejects_invalid_transition() -> None:
    with pytest.raises(LineWebhookTransitionError):
        transition_webhook_status(
            LineWebhookProcessingStatus.PENDING,
            LineWebhookProcessingStatus.PROCESSED,
        )


def test_webhook_retry_can_return_to_pending() -> None:
    result = transition_webhook_status(
        LineWebhookProcessingStatus.RETRYABLE_FAILED,
        LineWebhookProcessingStatus.PENDING,
    )

    assert result is LineWebhookProcessingStatus.PENDING

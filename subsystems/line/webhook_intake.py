"""Canonical LINE webhook intake: verify, normalize, store atomically, then wake."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from domains.line.identities import (
    LineDestinationId,
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
)
from domains.line.webhook import build_line_webhook_event
from shared_kernel.identities import CorrelationId
from subsystems.line.ports import LineUnitOfWorkPort, LineWakeupPublisherPort
from subsystems.line.webhook_contracts import LineWebhookRegistrationOutcome


class InvalidLineWebhookSignatureError(ValueError):
    pass


class InvalidLineWebhookPayloadError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LineWebhookIntakeResult:
    created_count: int
    duplicate_count: int


class LineWebhookIntake:
    def __init__(
        self,
        signature_verifier: object,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        wakeup_publisher: LineWakeupPublisherPort,
    ) -> None:
        self._signature_verifier = signature_verifier
        self._unit_of_work_factory = unit_of_work_factory
        self._wakeup_publisher = wakeup_publisher

    def accept(
        self,
        raw_body: bytes,
        signature: str | None,
        correlation_id: CorrelationId,
    ) -> LineWebhookIntakeResult:
        if not self._signature_verifier.verify(raw_body, signature):
            raise InvalidLineWebhookSignatureError("invalid LINE webhook signature")
        envelope = _parse_envelope(raw_body)
        events = _canonical_events(envelope)
        created_count = self._store(events, correlation_id)
        if created_count:
            self._publish_wakeup_best_effort()
        return LineWebhookIntakeResult(created_count, len(events) - created_count)

    def _store(self, events, correlation_id: CorrelationId) -> int:
        created_count = 0
        with self._unit_of_work_factory() as unit_of_work:
            for event in events:
                result = unit_of_work.webhook_inbox.register(event)
                if result.outcome is LineWebhookRegistrationOutcome.CREATED:
                    created_count += 1
            unit_of_work.commit()
        return created_count

    def _publish_wakeup_best_effort(self) -> None:
        try:
            self._wakeup_publisher.publish()
        except Exception as error:
            print(f"[LINE Webhook] Redis wake signal failed; DB fallback remains active: {error}")


def _parse_envelope(raw_body: bytes) -> Mapping[str, object]:
    try:
        envelope = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidLineWebhookPayloadError("invalid LINE webhook JSON") from error
    if not isinstance(envelope, dict) or not isinstance(envelope.get("events"), list):
        raise InvalidLineWebhookPayloadError("LINE webhook events must be a list")
    return envelope


def _canonical_events(envelope: Mapping[str, object]):
    raw_events = envelope["events"]
    if not raw_events:
        return ()
    destination = envelope.get("destination")
    if not isinstance(destination, str) or not destination.strip():
        raise InvalidLineWebhookPayloadError("LINE webhook destination is required")
    return tuple(_canonical_event(event, destination) for event in raw_events)


def _canonical_event(raw_event: object, destination: str):
    if not isinstance(raw_event, dict):
        raise InvalidLineWebhookPayloadError("LINE webhook event must be an object")
    event_type = raw_event.get("type")
    timestamp = raw_event.get("timestamp")
    if not isinstance(event_type, str) or not isinstance(timestamp, int):
        raise InvalidLineWebhookPayloadError("LINE webhook type and timestamp are required")
    delivery_context = raw_event.get("deliveryContext")
    is_redelivery = (
        bool(delivery_context.get("isRedelivery", False))
        if isinstance(delivery_context, dict)
        else False
    )
    return build_line_webhook_event(
        provider_event_id=_optional_text(raw_event.get("webhookEventId")),
        destination_id=LineDestinationId(destination),
        event_type=event_type,
        source=_source_identity(raw_event.get("source")),
        occurred_at=datetime.fromtimestamp(timestamp / 1000, timezone.utc),
        canonical_payload=raw_event,
        is_redelivery=is_redelivery,
    )


def _source_identity(raw_source: object) -> LineSourceIdentity:
    if not isinstance(raw_source, dict):
        raise InvalidLineWebhookPayloadError("LINE webhook source is required")
    try:
        source_type = LineSourceType(str(raw_source["type"]))
        identity_fields = {
            LineSourceType.USER: "userId",
            LineSourceType.GROUP: "groupId",
            LineSourceType.ROOM: "roomId",
        }
        source_id = str(raw_source[identity_fields[source_type]])
    except (KeyError, ValueError) as error:
        raise InvalidLineWebhookPayloadError("LINE webhook source is invalid") from error
    raw_user_id = raw_source.get("userId")
    user_id = LineUserId(str(raw_user_id)) if raw_user_id else None
    return LineSourceIdentity(source_type, source_id, user_id)


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def webhook_request_fingerprint(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


__all__ = [
    "InvalidLineWebhookPayloadError",
    "InvalidLineWebhookSignatureError",
    "LineWebhookIntake",
    "LineWebhookIntakeResult",
    "webhook_request_fingerprint",
]

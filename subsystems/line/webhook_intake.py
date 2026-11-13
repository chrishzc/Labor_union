"""Canonical LINE webhook intake: verify, normalize, store atomically, then wake."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from domains.line.delivery import LineDeliveryTaskSnapshot
from domains.line.identities import (
    LineDestinationId,
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
)
from domains.line.webhook import LineWebhookInboxSnapshot, build_line_webhook_event
from shared_kernel.identities import CorrelationId
from subsystems.line.ports import LineUnitOfWorkPort, LineWakeupPublisherPort
from subsystems.line.webhook_contracts import ClaimLineWebhookEventsQuery, LineWebhookRegistrationOutcome
from subsystems.line.webhook_event_consumer import RegisteredReply


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
        *,
        reply_consumer: Callable[[LineWebhookInboxSnapshot], RegisteredReply] | None = None,
        reply_delivery: Callable[[LineDeliveryTaskSnapshot], None] | None = None,
        release_after_reply: Callable[[LineWebhookInboxSnapshot], None] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        configured = (reply_consumer is not None, reply_delivery is not None, release_after_reply is not None)
        if any(configured) and not all(configured):
            raise ValueError("LINE webhook Reply requires processing, delivery and inbox release")
        self._signature_verifier = signature_verifier
        self._unit_of_work_factory = unit_of_work_factory
        self._wakeup_publisher = wakeup_publisher
        self._reply_consumer = reply_consumer
        self._reply_delivery = reply_delivery
        self._release_after_reply = release_after_reply
        self._now = now

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
        created_count, reserved = self._store(events)
        replies = []
        for event in reserved:
            try:
                replies.append(self._reply_consumer(event))
            except Exception as error:
                print(f"[LINE Webhook] Reply processing unavailable: {type(error).__name__}")
        for reply in replies:
            for task in reply.tasks:
                try:
                    self._reply_delivery(task)
                except Exception as error:
                    print(f"[LINE Webhook] Reply delivery unavailable: {type(error).__name__}")
            if reply.deferred_event is not None and self._release_after_reply is not None:
                try:
                    self._release_after_reply(reply.deferred_event)
                except Exception as error:
                    print(f"[LINE Webhook] Reply event release unavailable: {type(error).__name__}")
        if created_count:
            self._publish_wakeup_best_effort()
        return LineWebhookIntakeResult(created_count, len(events) - created_count)

    def _store(self, events):
        created_count = 0
        reserved = []
        query = ClaimLineWebhookEventsQuery("webhook-reply", self._now(), 1)
        with self._unit_of_work_factory() as unit_of_work:
            for event in events:
                result = unit_of_work.webhook_inbox.register(event)
                if result.outcome is LineWebhookRegistrationOutcome.CREATED:
                    created_count += 1
                    if self._reply_consumer is not None and _can_dispatch_reply(event):
                        reserved.append(unit_of_work.webhook_inbox.claim_registered(event.event_id, query))
            unit_of_work.commit()
        return created_count, reserved

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
    raw_event = {key: value for key, value in raw_event.items() if key != "immediate_reply_sent"}
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


def _can_dispatch_reply(event) -> bool:
    payload = json.loads(event.payload_json)
    if event.event_type == "postback":
        return True
    message = payload.get("message")
    return event.event_type == "message" and isinstance(message, dict) and message.get("type") == "text"


def webhook_request_fingerprint(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


__all__ = [
    "InvalidLineWebhookPayloadError",
    "InvalidLineWebhookSignatureError",
    "LineWebhookIntake",
    "LineWebhookIntakeResult",
    "webhook_request_fingerprint",
]

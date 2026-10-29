"""Recipient-bound LINE postback adapter for the candidate contact pool."""

from __future__ import annotations

from subsystems.line.message_copy import CANDIDATE_WILLING_RECEIVED
from subsystems.line.message_copy_catalog import configured_payload

import hashlib
import json
import re

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineSourceType
from shared_kernel.identities import CorrelationId, IdempotencyKey

_CANDIDATE_CONTACT_POSTBACK = re.compile(
    r"^candidate-contact:([0-9a-f]{64}):(willing|unwilling)$"
)


class LineCandidateContactPostbackApplication:
    def handle(self, inbox, unit_of_work) -> bool:
        event = inbox.event
        if event.source.source_type is not LineSourceType.USER:
            return False
        line_user_id = event.source.user_id
        if line_user_id is None:
            return False
        match = _CANDIDATE_CONTACT_POSTBACK.fullmatch(_postback_data(inbox))
        if match is None:
            return False
        try:
            unit_of_work.candidate_contact_pool_replies.record_willingness(
                match.group(1),
                match.group(2),
                line_user_id,
                IdempotencyKey(
                    "candidate-contact-postback:"
                    + hashlib.sha256(event.event_id.value.encode("utf-8")).hexdigest()
                ),
            )
        except (LookupError, ValueError):
            pass
        if match.group(2) == "willing":
            unit_of_work.delivery_tasks.enqueue(LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, line_user_id),
                LineMessageKind.TEXT,
                canonical_line_payload_json(configured_payload(unit_of_work, "candidate-willing-received", {
                    "type": "text",
                    "text": CANDIDATE_WILLING_RECEIVED,
                })),
                event.occurred_at,
                IdempotencyKey("candidate-willing-ack:" + hashlib.sha256(
                    event.event_id.value.encode("utf-8")
                ).hexdigest()),
                CorrelationId("candidate-willing-ack:" + event.event_id.value),
                "line_webhook_event",
                event.event_id.value,
            ))
        return True


def _postback_data(inbox) -> str:
    payload = json.loads(inbox.event.payload_json)
    postback = payload.get("postback")
    if not isinstance(postback, dict):
        return ""
    data = postback.get("data")
    return data.strip() if isinstance(data, str) else ""


__all__ = ["LineCandidateContactPostbackApplication"]

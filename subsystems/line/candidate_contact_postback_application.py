"""
File: candidate_contact_postback_application.py
Description: 轉送候選月嫂 LINE 意願 Postback，並建立 Reply-only 確認回覆。
"""

from __future__ import annotations

from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.message_copy import CANDIDATE_WILLING_RECEIVED

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
        event_digest = hashlib.sha256(event.event_id.value.encode("utf-8")).hexdigest()
        try:
            unit_of_work.candidate_contact_pool_replies.record_willingness(
                match.group(1),
                match.group(2),
                line_user_id,
                IdempotencyKey("candidate-contact-postback:" + event_digest),
            )
        except (LookupError, ValueError):
            return True
        reply_key = IdempotencyKey("candidate-willing-ack:" + event_digest)
        if unit_of_work.delivery_tasks.exists_for_key(reply_key):
            return True
        unit_of_work.delivery_tasks.enqueue(LineDeliveryRequest(
            LineRecipient(LineRecipientType.USER, line_user_id),
            LineMessageKind.TEXT,
            canonical_line_payload_json({"type": "text", "text": CANDIDATE_WILLING_RECEIVED}),
            event.occurred_at,
            reply_key,
            CorrelationId("line-event:" + event.event_id.value),
            REPLY_ONLY_WEBHOOK_SOURCE,
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

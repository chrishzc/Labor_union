"""
File: webhook_immediate_reply.py
Description: 在 Webhook 進入點以 Reply API 回應專人服務請求；失敗不回退 Push，工單由背景流程保存。
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineSourceType
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.runtime_human_escalation_source import normalize_complaint_text
from subsystems.line.deterministic_ai_router import is_confirmed_human_request
from subsystems.line.message_copy import CONTACT_RECEIVED
from subsystems.line.message_copy_catalog import configured_payload

_HANDOFF_CONFIRM_POSTBACK = "customer-service:handoff:confirm"



def enqueue_handoff_reply(inbox, unit) -> bool:
    """The acknowledgement only confirms receipt. The ticket stays in the background."""
    event = inbox.event
    if event.source.source_type is not LineSourceType.USER or event.source.user_id is None:
        return False
    if not _is_customer_service_handoff_event(json.loads(event.payload_json)):
        return False
    event_id = event.event_id.value
    key = IdempotencyKey(f"service-handoff-reply:{event_id}")
    unit.delivery_tasks.enqueue(LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, event.source.user_id), LineMessageKind.TEXT,
        canonical_line_payload_json(configured_payload(unit, "service-contact", {"type": "text", "text": CONTACT_RECEIVED})),
        event.occurred_at, key, CorrelationId(f"line-event:{event_id}"),
        REPLY_ONLY_WEBHOOK_SOURCE, event_id,
    ))
    return True


def _is_customer_service_handoff_event(raw_event: Mapping[str, Any]) -> bool:
    event_type = raw_event.get("type")
    if event_type == "postback":
        postback = raw_event.get("postback")
        data = postback.get("data") if isinstance(postback, Mapping) else None
        return isinstance(data, str) and data.strip() == _HANDOFF_CONFIRM_POSTBACK
    if event_type == "message":
        message = raw_event.get("message")
        if isinstance(message, Mapping) and message.get("type") == "text":
            text = message.get("text")
            return isinstance(text, str) and is_confirmed_human_request(text) and normalize_complaint_text(text) is None
    return False

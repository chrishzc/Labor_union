"""
File: webhook_immediate_reply.py
Description: 舊聯絡專人按鈕只回覆官方聊天室留言指引。
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineSourceType
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE

_HANDOFF_CONFIRM_POSTBACK = "customer-service:handoff:confirm"


def enqueue_retired_handoff_reply(inbox, unit) -> bool:
    event = inbox.event
    if event.source.source_type is not LineSourceType.USER or event.source.user_id is None:
        return False
    if not _is_customer_service_handoff_event(json.loads(event.payload_json)):
        return False
    event_id = event.event_id.value
    key = IdempotencyKey(f"service-handoff-retired-reply:{event_id}")
    unit.delivery_tasks.enqueue(LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, event.source.user_id), LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": "如需協助，請直接在此官方帳號聊天室留言。"}),
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
    return False

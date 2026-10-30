"""
File: webhook_immediate_reply.py
Description: 在 Webhook 進入點以 Reply API 回應專人服務請求；失敗不回退 Push，工單由背景流程保存。
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Protocol

from subsystems.line.deterministic_ai_router import is_confirmed_human_request
from subsystems.line.message_copy import CONTACT_RECEIVED

_HANDOFF_CONFIRM_POSTBACK = "customer-service:handoff:confirm"
IMMEDIATE_REPLY_SENT_KEY = "immediate_reply_sent"


class LineReplyPort(Protocol):
    def reply(self, reply_token: str, message: dict[str, Any]) -> Any:
        ...


class LineWebhookImmediateReplyService:
    """以 Reply API 受理專員呼叫；不可使用時略過回覆，不影響工單保存。"""

    def __init__(self, reply_adapter: LineReplyPort, copy_reader=None) -> None:
        self._reply_adapter = reply_adapter
        self._copy_reader = copy_reader

    def is_customer_service_handoff_event(self, raw_event: Mapping[str, Any]) -> bool:
        if not isinstance(raw_event, Mapping):
            return False
        event_type = raw_event.get("type")
        if event_type == "postback":
            postback = raw_event.get("postback")
            if isinstance(postback, Mapping):
                data = postback.get("data")
                return isinstance(data, str) and data.strip() == _HANDOFF_CONFIRM_POSTBACK
            return False
        if event_type == "message":
            message = raw_event.get("message")
            if isinstance(message, Mapping) and message.get("type") == "text":
                text = message.get("text")
                return isinstance(text, str) and is_confirmed_human_request(text)
            return False
        return False

    def try_immediate_reply(self, raw_event: dict[str, Any]) -> bool:
        if not self.is_customer_service_handoff_event(raw_event):
            return False
        reply_token = raw_event.get("replyToken")
        if not isinstance(reply_token, str) or not reply_token.strip():
            return False
        if raw_event.get(IMMEDIATE_REPLY_SENT_KEY) is True:
            return True

        try:
            text = self._copy_reader() if self._copy_reader is not None else CONTACT_RECEIVED
            message_payload = {"type": "text", "text": text}
            outcome = self._reply_adapter.reply(reply_token.strip(), message_payload)
            outcome_type = getattr(outcome, "outcome_type", None)
            is_success = (
                getattr(outcome_type, "value", None) == "success"
                or str(outcome_type).lower() == "success"
                or getattr(outcome, "provider_message_id", None) is not None
            )
            if is_success:
                raw_event[IMMEDIATE_REPLY_SENT_KEY] = True
                return True
        except Exception as error:
            print(
                "[LINE Immediate Reply] Acknowledgement skipped; Push fallback disabled "
                f"({type(error).__name__})"
            )
        return False


def is_immediate_reply_sent(inbox_or_payload: Any) -> bool:
    """判斷該事件是否已在 Webhook 階段成功完成即時回傳。"""
    if inbox_or_payload is None:
        return False
    if isinstance(inbox_or_payload, Mapping):
        return bool(inbox_or_payload.get(IMMEDIATE_REPLY_SENT_KEY, False))
    # 支援 CanonicalLineWebhookEvent 或 LineWebhookInboxSnapshot
    payload_json = getattr(inbox_or_payload, "payload_json", None)
    if payload_json is None:
        event = getattr(inbox_or_payload, "event", None)
        payload_json = getattr(event, "payload_json", None)
    if isinstance(payload_json, str):
        try:
            parsed = json.loads(payload_json)
            if isinstance(parsed, Mapping):
                return bool(parsed.get(IMMEDIATE_REPLY_SENT_KEY, False))
        except Exception:
            return False
    return False


__all__ = [
    "IMMEDIATE_REPLY_SENT_KEY",
    "LineReplyPort",
    "LineWebhookImmediateReplyService",
    "is_immediate_reply_sent",
]

"""Canonical LINE webhook handlers for friend state and identity-flow entry points."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Callable

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identity_flow import LineIdentityFlowPurpose
from domains.line.platform_user import LineFriendEvent, LineFriendEventType
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.identity_contracts import OpenLineIdentityFlowCommand

_STAFF_COMMAND = "我是月嫂"
_ADMIN_COMMANDS = {"綁定system_admin", "綁定工會帳號"}
_CUSTOMER_COMMANDS = {"綁定", "查詢訂單"}


class LineWebhookIdentityHandlers:
    def __init__(
        self,
        now: Callable[[], datetime],
        identity_url: Callable[[str, str], str],
        *,
        flow_lifetime: timedelta = timedelta(minutes=15),
        follow_scheduler: Callable[[object, object, object], int] | None = None,
        media_scheduler: Callable[[object, object], bool] | None = None,
    ) -> None:
        self._now = now
        self._identity_url = identity_url
        self._flow_lifetime = flow_lifetime
        self._follow_scheduler = follow_scheduler
        self._media_scheduler = media_scheduler

    def registry(self):
        return {
            "follow": self.handle_follow,
            "unfollow": self.handle_unfollow,
            "message": self.handle_message,
        }

    def handle_follow(self, inbox, unit_of_work):
        line_user_id = _required_user_id(inbox)
        unit_of_work.platform_users.apply_friend_event(
            _friend_event(inbox, line_user_id, LineFriendEventType.FOLLOW)
        )
        if self._follow_scheduler is not None:
            self._follow_scheduler(inbox, unit_of_work, line_user_id)
        self._open_and_notify(
            inbox,
            unit_of_work,
            line_user_id,
            LineIdentityFlowPurpose.CUSTOMER_BINDING,
        )

    def handle_unfollow(self, inbox, unit_of_work):
        line_user_id = _required_user_id(inbox)
        unit_of_work.platform_users.apply_friend_event(
            _friend_event(inbox, line_user_id, LineFriendEventType.UNFOLLOW)
        )
        unit_of_work.delivery_tasks.cancel_pending_for_recipient(line_user_id)

    def handle_message(self, inbox, unit_of_work):
        line_user_id = _optional_user_id(inbox)
        if line_user_id is None:
            return
        unit_of_work.platform_users.apply_friend_event(
            _friend_event(inbox, line_user_id, LineFriendEventType.ACTIVITY)
        )
        if self._media_scheduler is not None and self._media_scheduler(inbox, unit_of_work):
            return
        text = _message_text(inbox)
        if text is None:
            return
        purpose = _identity_purpose_for_text(text)
        if purpose is None:
            return
        self._open_and_notify(inbox, unit_of_work, line_user_id, purpose)

    # Kept cohesive so the flow and its delivery task use the same event identity.
    def _open_and_notify(self, inbox, unit_of_work, line_user_id, purpose):
        event_identity = inbox.event.event_id.value
        correlation_id = CorrelationId(f"line-event:{event_identity}")
        opened = unit_of_work.identity_flows.open(
            OpenLineIdentityFlowCommand(
                purpose,
                line_user_id,
                self._now() + self._flow_lifetime,
                IdempotencyKey(f"identity-flow:{purpose.value}:{event_identity}"),
                correlation_id,
            )
        )
        url = self._identity_url(purpose.value, opened.flow_id.value)
        unit_of_work.delivery_tasks.enqueue(
            _identity_link_delivery(
                line_user_id,
                purpose,
                url,
                event_identity,
                correlation_id,
                self._now(),
            )
        )


def _identity_link_delivery(
    line_user_id,
    purpose,
    url,
    event_identity,
    correlation_id,
    scheduled_at,
):
    message = _identity_link_message(purpose, url)
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, line_user_id),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": message}),
        scheduled_at,
        IdempotencyKey(f"identity-link:{purpose.value}:{event_identity}"),
        correlation_id,
        "line_webhook_event",
        event_identity,
    )


def _identity_link_message(purpose, url):
    introductions = {
        LineIdentityFlowPurpose.CUSTOMER_BINDING: "請開啟以下頁面完成客戶資料綁定：",
        LineIdentityFlowPurpose.STAFF_VERIFICATION: "請開啟以下頁面填寫月嫂身分資料：",
        LineIdentityFlowPurpose.ADMIN_BINDING: "請開啟以下頁面登入並綁定工會後台帳號：",
    }
    return f"{introductions[purpose]}\n\n{url}\n\n此連結將於 15 分鐘後失效。"


def _identity_purpose_for_text(text):
    normalized = text.strip()
    if _STAFF_COMMAND in normalized:
        return LineIdentityFlowPurpose.STAFF_VERIFICATION
    if normalized in _ADMIN_COMMANDS:
        return LineIdentityFlowPurpose.ADMIN_BINDING
    if normalized in _CUSTOMER_COMMANDS:
        return LineIdentityFlowPurpose.CUSTOMER_BINDING
    return None


def _message_text(inbox):
    payload = json.loads(inbox.event.payload_json)
    message = payload.get("message")
    if not isinstance(message, dict) or message.get("type") != "text":
        return None
    text = message.get("text")
    return text if isinstance(text, str) and text.strip() else None


def _required_user_id(inbox):
    line_user_id = _optional_user_id(inbox)
    if line_user_id is None:
        raise ValueError("LINE identity event requires a user source")
    return line_user_id


def _optional_user_id(inbox):
    return inbox.event.source.user_id


def _friend_event(inbox, line_user_id, event_type):
    return LineFriendEvent(
        line_user_id,
        inbox.event.event_id,
        event_type,
        inbox.event.occurred_at,
    )


__all__ = ["LineWebhookIdentityHandlers"]

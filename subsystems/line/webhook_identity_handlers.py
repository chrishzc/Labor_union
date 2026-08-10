"""Canonical LINE webhook handlers for friend state and identity-flow entry points."""

from __future__ import annotations

import json
import os
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
_SERVICE_HELP_COMMAND = "服務說明"
_SERVICE_HELP_CATEGORIES = {
    "服務流程": (
        "服務流程如下：\n\n"
        "1. 先完成服務登記。\n"
        "2. 工會確認您的資料與服務期程。\n"
        "3. 系統篩選可配合的月嫂。\n"
        "4. 月嫂同意接案後，工會提供月嫂資料給您確認。\n"
        "5. 雙方確認後，進入後續媒合與簽約流程。\n\n"
        "如您尚未登記，請點選下方選單的「服務登記」。"
    ),
    "收費與補助": (
        "收費與補助說明：\n\n"
        "實際費用會依服務天數、每日服務時數、服務地點與個案條件確認。"
        "若要申請補助，請於服務登記時填寫身分證字號與戶籍資料，工會會再依規範協助確認資格。"
    ),
    "查詢服務進度": (
        "若要查詢服務進度，請先完成服務登記或帳號綁定。\n\n"
        "已完成登記者，請回覆您的案件編號或登記姓名，工會人員會依資料協助確認目前進度。"
    ),
    "修改登記資料": (
        "若要修改已送出的登記資料，請開啟下方頁面填寫資料異動申請。"
        "送出後資料會先暫存，待工會人員審核通過後才會正式更新。"
    ),
    "聯絡工會人員": (
        "如需工會人員協助，請直接在此聊天室留下您的問題、案件編號或聯絡電話。"
        "工會人員確認後會再協助回覆。"
    ),
    "月嫂身分認證": "若您是月嫂本人，請點選下方「我是月嫂」或直接回覆「我是月嫂」，系統會送出身分確認申請。",
    "其他問題": (
        "請直接輸入您的問題內容。若已經有案件編號，也請一起提供，方便工會人員協助查詢。"
    ),
}
_SERVICE_HELP_CATEGORY_KEYS = {
    "服務流程": "service-flow",
    "收費與補助": "payment-subsidy",
    "查詢服務進度": "service-progress",
    "修改登記資料": "profile-update",
    "聯絡工會人員": "contact-union",
    "月嫂身分認證": "staff-verification",
    "其他問題": "other",
}


class LineWebhookIdentityHandlers:
    def __init__(
        self,
        now: Callable[[], datetime],
        identity_url: Callable[[str, str], str],
        *,
        flow_lifetime: timedelta = timedelta(minutes=15),
        follow_scheduler: Callable[[object, object, object], int] | None = None,
        media_scheduler: Callable[[object, object], bool] | None = None,
        group_application: object | None = None,
        matching_postback_application: object | None = None,
        knowledge_question_scheduler: Callable[[object, object, object, str], object] | None = None,
    ) -> None:
        self._now = now
        self._identity_url = identity_url
        self._flow_lifetime = flow_lifetime
        self._follow_scheduler = follow_scheduler
        self._media_scheduler = media_scheduler
        self._group_application = group_application
        self._matching_postback_application = matching_postback_application
        self._knowledge_question_scheduler = knowledge_question_scheduler

    def registry(self):
        return {
            "follow": self.handle_follow,
            "unfollow": self.handle_unfollow,
            "message": self.handle_message,
            "memberJoined": self.handle_group_membership,
            "memberLeft": self.handle_group_membership,
            "postback": self.handle_postback,
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
        if self._group_application is not None and self._group_application.handle_message(
            inbox, unit_of_work
        ):
            return
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
            if _handle_service_help_text(
                inbox,
                unit_of_work,
                line_user_id,
                text,
                self._now(),
            ):
                return
            if self._knowledge_question_scheduler is not None:
                self._knowledge_question_scheduler(inbox, unit_of_work, line_user_id, text)
            return
        source_type = getattr(inbox.event.source, "source_type", None)
        if source_type is not None and source_type.value != "user":
            return
        self._open_and_notify(inbox, unit_of_work, line_user_id, purpose)

    def handle_group_membership(self, inbox, unit_of_work):
        if self._group_application is not None:
            self._group_application.handle_membership(inbox, unit_of_work)

    def handle_postback(self, inbox, unit_of_work):
        if self._matching_postback_application is not None:
            self._matching_postback_application.handle(inbox, unit_of_work)

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


def _handle_service_help_text(inbox, unit_of_work, line_user_id, text, scheduled_at):
    normalized = text.strip()
    event_identity = inbox.event.event_id.value
    correlation_id = CorrelationId(f"line-event:{event_identity}")
    if normalized == _SERVICE_HELP_COMMAND:
        unit_of_work.delivery_tasks.enqueue(
            _service_help_menu_delivery(
                line_user_id,
                event_identity,
                correlation_id,
                scheduled_at,
            )
        )
        return True
    if normalized not in _SERVICE_HELP_CATEGORIES:
        return False
    reply_text = _SERVICE_HELP_CATEGORIES[normalized]
    if normalized == "修改登記資料":
        reply_text = f"{reply_text}\n\n{_liff_url('?target=profile_update')}"
    payload = _text_message_payload(reply_text)
    if normalized == "月嫂身分認證":
        payload["quickReply"] = {"items": [_quick_reply_item("我是月嫂")]}
    unit_of_work.delivery_tasks.enqueue(
        _text_delivery(
            line_user_id,
            payload,
            event_identity,
            correlation_id,
            scheduled_at,
            f"service-help-category:{_SERVICE_HELP_CATEGORY_KEYS[normalized]}:{event_identity}",
        )
    )
    return True


def _service_help_menu_delivery(
    line_user_id,
    event_identity,
    correlation_id,
    scheduled_at,
):
    payload = {
        "type": "text",
        "text": "請選擇您想了解或處理的項目：",
        "quickReply": {
            "items": [
                _quick_reply_item(label)
                for label in _SERVICE_HELP_CATEGORIES
            ]
        },
    }
    return _text_delivery(
        line_user_id,
        payload,
        event_identity,
        correlation_id,
        scheduled_at,
        f"service-help-menu:{event_identity}",
    )


def _quick_reply_item(label):
    return {
        "type": "action",
        "action": {
            "type": "message",
            "label": label,
            "text": label,
        },
    }


def _text_message_payload(text):
    return {"type": "text", "text": text}


def _text_delivery(
    line_user_id,
    payload,
    event_identity,
    correlation_id,
    scheduled_at,
    idempotency_key,
):
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, line_user_id),
        LineMessageKind.TEXT,
        canonical_line_payload_json(payload),
        scheduled_at,
        IdempotencyKey(idempotency_key),
        correlation_id,
        "line_webhook_event",
        event_identity,
    )


def _liff_url(query):
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id:
        return "LIFF 尚未完成設定，請聯絡工會人員。"
    return f"https://liff.line.me/{liff_id}/{query}"


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

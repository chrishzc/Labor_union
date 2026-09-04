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
_ADMIN_COMMANDS = {"綁定system_admin", "綁定工會帳號", "綁定後台帳號"}
_CUSTOMER_COMMANDS = {"服務登記", "綁定", "查詢訂單", "綁定訂單", "訂單查詢"}
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
        "若要修改已送出的登記資料，請直接回覆要修改的項目與正確內容。"
        "工會人員核對後會人工補登；此對話不會直接變更正式資料。"
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
        service_help_application: object | None = None,
        menu_command_application: object | None = None,
    ) -> None:
        self._now = now
        self._identity_url = identity_url
        self._flow_lifetime = flow_lifetime
        self._follow_scheduler = follow_scheduler
        self._media_scheduler = media_scheduler
        self._group_application = group_application
        self._matching_postback_application = matching_postback_application
        self._knowledge_question_scheduler = knowledge_question_scheduler
        self._service_help_application = service_help_application
        self._menu_command_application = menu_command_application

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
        if self._matching_postback_application is not None and self._matching_postback_application.handle_message(
            inbox,
            unit_of_work,
            line_user_id,
            text,
        ):
            return
        purpose = _identity_purpose_for_text(text)
        if purpose is None:
            normalized = text.strip()
            if normalized in {"有幫助", "👍 有幫助", "很有幫助", "有解決"}:
                self._handle_feedback_resolved(inbox, unit_of_work, line_user_id)
                return
            if normalized in {"未解決", "👎 未解決", "沒解決", "沒有幫助", "未解決（通報專人客服）"}:
                self._handle_feedback_unresolved(inbox, unit_of_work, line_user_id)
                return
            if self._menu_command_application is not None and self._menu_command_application.handle(
                inbox, unit_of_work, line_user_id, text
            ):
                return
            if self._handle_service_help(
                inbox,
                unit_of_work,
                line_user_id,
                text,
            ):
                return
            if self._knowledge_question_scheduler is not None:
                self._knowledge_question_scheduler(inbox, unit_of_work, line_user_id, text)
            return
        source_type = getattr(inbox.event.source, "source_type", None)
        if source_type is not None and source_type.value != "user":
            return
        self._open_and_notify(inbox, unit_of_work, line_user_id, purpose)

    def _handle_service_help(self, inbox, unit_of_work, line_user_id, text) -> bool:
        if self._service_help_application is not None:
            return self._service_help_application.handle(
                inbox,
                unit_of_work,
                line_user_id,
                text,
            )
        return _handle_service_help_text(
            inbox,
            unit_of_work,
            line_user_id,
            text,
            self._now(),
        )

    def handle_group_membership(self, inbox, unit_of_work):
        if self._group_application is not None:
            self._group_application.handle_membership(inbox, unit_of_work)

    def handle_postback(self, inbox, unit_of_work):
        if self._matching_postback_application is not None:
            self._matching_postback_application.handle(inbox, unit_of_work)

    def _handle_feedback_resolved(self, inbox, unit_of_work, line_user_id) -> None:
        event_identity = inbox.event.event_id.value
        correlation_id = CorrelationId(inbox.event.correlation_id.value)
        delivery = _text_delivery(
            line_user_id,
            _text_message_payload("感謝您的肯定與回饋！很高興能為您解答 😊 若還有其他疑問，歡迎隨時告訴小幫手。"),
            event_identity,
            correlation_id,
            self._now(),
            f"feedback-resolved:{event_identity}",
        )
        unit_of_work.delivery_tasks.enqueue(delivery)

    def _handle_feedback_unresolved(self, inbox, unit_of_work, line_user_id) -> None:
        event_identity = inbox.event.event_id.value
        correlation_id = CorrelationId(inbox.event.correlation_id.value)
        ticket_id_str = ""
        if hasattr(unit_of_work, "customer_service") and unit_of_work.customer_service is not None:
            try:
                from domains.customer_service.ticket import CustomerServiceCategory
                from subsystems.customer_service.contracts import CreateCustomerServiceMessage
                ticket = unit_of_work.customer_service.create_or_append(
                    CreateCustomerServiceMessage(
                        line_user_id=line_user_id.value,
                        category=CustomerServiceCategory.OTHER,
                        message="LINE 知識庫問答用戶回饋未解決，請真人客服接手協助。",
                        event_key=f"line-feedback-ticket:{event_identity}",
                    )
                )
                ticket_id_str = f"（工單編號 #{ticket.ticket_id}）"
            except Exception:
                pass

        delivery = _text_delivery(
            line_user_id,
            _text_message_payload(f"已收到您的回饋！我們已為您通報工會專人客服{ticket_id_str}，專員將盡快接手與您聯繫協助，請稍候！"),
            event_identity,
            correlation_id,
            self._now(),
            f"feedback-unresolved:{event_identity}",
        )
        unit_of_work.delivery_tasks.enqueue(delivery)

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
    if purpose == LineIdentityFlowPurpose.CUSTOMER_BINDING:
        return (
            "您好！歡迎加入【新竹市月子工會】官方服務平台 🤱✨\n\n"
            "我們提供專業、安心、有保障的到府坐月子媒合與母嬰照護服務。\n\n"
            "📱【新手快速導覽・三步驟開始使用】\n\n"
            "1️⃣ 準爸媽／產婦專區：\n"
            "👉 請開啟以下專屬登記頁面，進行服務需求填寫或核對市府登記案件：\n"
            f"{url}\n"
            "（此安全登記連結將於 15 分鐘後失效）\n\n"
            "2️⃣ 專業月嫂服務人員：\n"
            "👉 請點擊下方選單【月嫂專區】或直接在對話框輸入「我要綁定月嫂」進行身分認證。\n\n"
            "3️⃣ 即時智慧客服諮詢：\n"
            "👉 直接在對話框輸入您的問題（例如：「補助時數」、「收費原則」、「服務內容」），AI 小幫手 24 小時為您即時解答！\n\n"
            "---\n"
            "💡 如需真人專員協助，隨時在對話框輸入「轉真人客服」，我們將由專人為您服務。\n\n"
            "👇 請點擊下方圖文選單，開啟您的專屬服務！"
        )
    introductions = {
        LineIdentityFlowPurpose.STAFF_VERIFICATION: "請開啟以下頁面填寫月嫂身分資料：",
        LineIdentityFlowPurpose.ADMIN_BINDING: "請開啟以下頁面登入並綁定工會後台帳號：",
    }
    intro = introductions.get(purpose, "請開啟以下頁面完成身分綁定：")
    return f"{intro}\n\n{url}\n\n此連結將於 15 分鐘後失效。"


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

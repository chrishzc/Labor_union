"""
File: service_help_application.py
Description: 將已核准的自助服務文字入口路由為 LINE 回覆。
"""

from __future__ import annotations

from subsystems.line.message_copy_catalog import configured_payload
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.navigation_catalog import route_aliases

from datetime import datetime, timedelta
import os
from typing import Callable

from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identity_flow import LineIdentityFlowPurpose
from domains.line.identities import LineSourceType
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.line.identity_contracts import OpenLineIdentityFlowCommand
from subsystems.line.ai_router_contracts import (
    Clarification,
    DeterministicAnswer,
    DeterministicRoute,
    SafeMenu,
    Unavailable,
)
from subsystems.line.deterministic_ai_router import DeterministicLineRouter
from subsystems.line.notification_policy import NotificationSourceEvent
from shared_kernel.identities import IdempotencyReceipt
from subsystems.line.runtime_human_escalation_source import normalize_complaint_text


_HANDOFF_WRONG_ANSWER_POSTBACK = "customer-service:handoff:confirm:answer-rejected"
_HANDOFF_CONTINUE_POSTBACK = "customer-service:handoff:continue-ai"
_HANDOFF_RESUME_POSTBACK = "customer-service:handoff:resume-ai"
_RESUME_AI_ALIASES = {
    "恢復ai助理",
    "恢復ai",
    "繼續使用ai",
    "恢復機器人",
    "恢復機器人回答",
    "繼續讓機器人回答",
}
_REPLY_ONLY_SUFFIXES = frozenset({
    "menu", "order-update-menu", "registration", "clarification", "unavailable",
    "retired-ai-action", "service_flow", "payment_subsidy", "service_progress", "profile-update-form", "other",
})


def _normalized_resume_command(text: str) -> str:
    return "".join(text.split()).casefold()


class LineServiceHelpApplication:
    def __init__(
        self,
        now: Callable[[], datetime],
        identity_url: Callable[[str, str], str] | None = None,
    ) -> None:
        self._now = now
        self._identity_url = identity_url
        self._router = DeterministicLineRouter()

    def handle(self, inbox, unit_of_work, line_user_id, text: str, *, reply_only: bool = False) -> bool:
        normalized = text.strip()
        resume_aliases = {
            _normalized_resume_command(alias)
            for alias in (route_aliases("resume_ai_assistant") or tuple(_RESUME_AI_ALIASES))
        }
        if _normalized_resume_command(normalized) in resume_aliases:
            self._retired_ai_action(inbox, unit_of_work, line_user_id)
            return True
        if normalize_complaint_text(normalized) is not None:
            return False
        event_id = inbox.event.event_id.value
        outcome = self._router.route(normalized, source_event_id=event_id)
        if reply_only and isinstance(outcome, DeterministicAnswer):
            return False
        if isinstance(outcome, DeterministicRoute):
            if outcome.route_key == "registration":
                self._reply_or_enqueue(
                    inbox,
                    unit_of_work,
                    line_user_id,
                    configured_payload(unit_of_work, "service-registration" if _registration_liff_url() else "service-registration-unavailable", _text_payload(_registration_reply(_registration_liff_url())), {"registration_url": _registration_liff_url()}),
                    "registration",
                    reason_code=outcome.reason_code,
                )
                return True
            if outcome.route_key == "service_help_menu":
                self._reply_or_enqueue(inbox, unit_of_work, line_user_id, _service_menu_payload(), "menu", reason_code=outcome.reason_code)
                return True
            if outcome.route_key in {"order_update_menu", "order_update_request"}:
                self._reply_or_enqueue(inbox, unit_of_work, line_user_id, _order_update_menu_payload(), "order-update-menu", reason_code=outcome.reason_code)
                return True
            if outcome.category is None:
                return False
            self._handle_category(inbox, unit_of_work, line_user_id, outcome.category)
            return True
        if isinstance(outcome, SafeMenu):
            return False
        if isinstance(outcome, Clarification):
            self._reply_or_enqueue(
                inbox,
                unit_of_work,
                line_user_id,
                _clarification_payload(outcome),
                "clarification",
                reason_code=outcome.reason_code,
            )
            return True
        if isinstance(outcome, DeterministicAnswer):
            self._reply_or_enqueue(
                inbox,
                unit_of_work,
                line_user_id,
                _answer_payload(outcome),
                "knowledge",
                reason_code="published_knowledge",
            )
            return True
        if isinstance(outcome, Unavailable):
            self._reply_or_enqueue(
                inbox,
                unit_of_work,
                line_user_id,
                _text_payload(outcome.human_action),
                "unavailable",
                reason_code=outcome.code,
            )
            return True
        return False

    def handle_postback(
        self, inbox, unit_of_work, line_user_id, postback_data: str
    ) -> bool:
        if postback_data not in {
            _HANDOFF_WRONG_ANSWER_POSTBACK,
            _HANDOFF_CONTINUE_POSTBACK,
            _HANDOFF_RESUME_POSTBACK,
        }:
            return False
        if line_user_id is not None and inbox.event.source.source_type is LineSourceType.USER:
            self._retired_ai_action(inbox, unit_of_work, line_user_id)
        return True

    def _retired_ai_action(self, inbox, unit_of_work, line_user_id) -> None:
        self._reply_or_enqueue(
            inbox,
            unit_of_work,
            line_user_id,
            _text_payload("此功能已停用。如需協助，請直接在此聊天室留言。"),
            "retired-ai-action",
            reason_code="chat_ai_retired",
        )

    def _handle_category(self, inbox, unit_of_work, line_user_id, category):
        if category in {CustomerServiceCategory.SERVICE_FLOW, CustomerServiceCategory.PAYMENT_SUBSIDY}:
            payload = _ai_assistant_payload()
        elif category is CustomerServiceCategory.SERVICE_PROGRESS:
            payload = self._progress_payload(inbox, unit_of_work, line_user_id)
        elif category is CustomerServiceCategory.PROFILE_UPDATE:
            payload = _profile_update_payload()
        else:
            payload = _service_menu_payload()
        suffix = "profile-update-form" if category is CustomerServiceCategory.PROFILE_UPDATE else category.value
        self._reply_or_enqueue(inbox, unit_of_work, line_user_id, payload, suffix)

    def _progress_payload(self, inbox, unit_of_work, line_user_id):
        context = unit_of_work.customer_service.latest_client_case(line_user_id.value)
        if context or self._identity_url is None:
            if not context:
                return _progress_payload(context)
            return configured_payload(unit_of_work, "service-progress", _progress_payload(context), {
                "case_no": (context or {}).get("case_no") or "尚未核發", "status": (context or {}).get("status") or "資料確認中",
                "start_date": (context or {}).get("start_date") or "未定", "end_date": (context or {}).get("end_date") or "未定"})
        event_id = inbox.event.event_id.value
        opened = unit_of_work.identity_flows.open(
            OpenLineIdentityFlowCommand(
                LineIdentityFlowPurpose.CUSTOMER_BINDING,
                line_user_id,
                self._now() + timedelta(minutes=15),
                IdempotencyKey(f"service-help-binding:{event_id}"),
                CorrelationId(f"line-event:{event_id}"),
            )
        )
        url = self._identity_url(opened.purpose.value, opened.flow_id.value)
        return configured_payload(unit_of_work, "service-progress-unbound", _text_payload(_unbound_progress_reply(url)), {"identity_url": url})

    def _enqueue(self, inbox, unit_of_work, line_user_id, payload, suffix, *, reason_code=None):
        event_id = inbox.event.event_id.value
        source = getattr(inbox.event, "source", None)
        same_private_chat = (
            getattr(source, "source_type", None) is LineSourceType.USER
            and getattr(source, "user_id", None) == line_user_id
        )
        copy_key = {"menu": "service-menu", "order-update-menu": "order-update-menu", "other": "service-menu"}.get(suffix)
        if copy_key:
            payload = configured_payload(unit_of_work, copy_key, payload)
        request = LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, line_user_id),
                LineMessageKind.FLEX if payload.get("type") == "flex" else LineMessageKind.TEXT,
                canonical_line_payload_json(payload), self._now(),
                IdempotencyKey(f"service-help:{suffix}:{event_id}"),
                CorrelationId(f"line-event:{event_id}"),
                REPLY_ONLY_WEBHOOK_SOURCE if same_private_chat and suffix in _REPLY_ONLY_SUFFIXES else "line_webhook_event", event_id,
            )
        delivery = unit_of_work.delivery_tasks.enqueue(request)
        notification_rules = getattr(unit_of_work, "notification_rules", None)
        receipts = getattr(unit_of_work, "receipts", None)
        register_source_event = getattr(notification_rules, "register_source_event", None)
        if callable(register_source_event):
            source_identity = f"router-reply:{event_id}:{suffix}"
            register_source_event(
                NotificationSourceEvent(
                    identity=source_identity,
                    event_code="router.deterministic.reply_committed",
                    historical_silent=False,
                    facts={
                        "source_event_id": event_id,
                        "reply_kind": suffix,
                        "reason_code": reason_code or suffix,
                        "source_contract_id": "LU96-M2-ROUTER-REPLY-SOURCE-V1",
                        "source_revision": 1,
                        "delivery_task_id": getattr(getattr(delivery, "task_id", None), "value", None),
                    },
                    source_domain="line_router",
                    source_aggregate_type="line_router_reply",
                    source_aggregate_identity=event_id,
                    source_version=1,
                    occurred_at=request.scheduled_at,
                )
            )
            if callable(getattr(receipts, "append", None)):
                receipts.append(
                    IdempotencyReceipt(
                        IdempotencyKey(f"line-router-reply:{source_identity}"),
                        fingerprint_payload({
                            "source_identity": source_identity,
                            "reply_kind": suffix,
                            "reason_code": reason_code or suffix,
                        }),
                        f"line-router-reply:{source_identity}",
                    )
                )

    def _reply_or_enqueue(self, inbox, unit_of_work, line_user_id, payload, suffix, *, reason_code=None):
        self._enqueue(inbox, unit_of_work, line_user_id, payload, suffix, reason_code=reason_code)

def _text_payload(text):
    return {"type": "text", "text": text}


def _progress_payload(context):
    if not context:
        return _text_payload("目前尚未找到您綁定的服務資料。請點選下方「服務登記」取得新的安全綁定入口。")
    dates = f"{context.get('start_date') or '未定'} 至 {context.get('end_date') or '未定'}"
    return _text_payload(f"最新案件：{context.get('case_no') or '尚未核發'}\n目前狀態：{context.get('status') or '資料確認中'}\n服務期間：{dates}")


def _unbound_progress_reply(identity_url):
    return (
        "目前尚未找到您綁定的服務資料。\n\n"
        "若您已填過資料，請開啟以下安全綁定入口：\n"
        f"{identity_url}\n\n"
        "若您是新客戶，請點選下方「服務登記」完成資料填寫。"
    )


def _registration_liff_url():
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id or liff_id == "your_liff_id_here":
        return None
    return f"https://liff.line.me/{liff_id}?entry=registration"


def _registration_reply(registration_url):
    if registration_url is None:
        return "服務登記入口尚未完成設定，請聯絡工會人員協助。"
    return f"請開啟以下服務登記頁面：\n\n{registration_url}"


def _ai_assistant_liff_url():
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id or liff_id == "your_liff_id_here":
        liff_id = "ai-assistant"
    return f"https://liff.line.me/{liff_id}?target=ai_assistant"


def _service_menu_payload():
    actions = (
        ("如何申請服務？", "ai_assistant", "secondary"),
        ("費用與補助怎麼算？", "ai_assistant", "secondary"),
        ("如何查詢目前進度？", "查詢服務進度", "secondary"),
        ("登記資料填錯怎麼辦？", "修改登記資料", "secondary"),
        ("詢問其他問題", "ai_assistant", "secondary"),
    )
    return _navigation_card_payload(
        alt_text="服務與問答：請選擇需要的協助",
        eyebrow="新竹市月子工會",
        title="服務與問答",
        description="常見問題與服務入口集中在這裡。如果沒看到想問的問題，可以試試看 AI 智慧問答！",
        actions=actions,
        hint="如需人員協助，請直接在此聊天室留言。",
    )


def _ai_assistant_payload():
    return _navigation_card_payload(
        alt_text="服務說明請至 AI 客服查看",
        eyebrow="新竹市月子工會",
        title="AI 客服與常見問答",
        description="服務流程、收費與補助等說明，請至 AI 客服查看常見問答或提問。",
        actions=(("開啟 AI 客服", "ai_assistant", "primary"),),
        hint="如需人員協助，請直接在此聊天室留言。",
    )


def _form_liff_url(target: str) -> str | None:
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id or liff_id == "your_liff_id_here":
        return None
    return f"https://liff.line.me/{liff_id}?target={target}"


def _profile_update_payload():
    return _text_payload("如需修改聯絡電話、服務地址或個人登記資料，請直接在此聊天室留言，工會專員將由後台為您即時調整與確認。")


def _order_update_liff_url():
    return None


def _order_update_menu_payload():
    return _text_payload("如需變更服務時段、服務天數或訂單內容，請直接在此聊天室留言，工會專員將由後台為您即時確認與調整。")


def _navigation_card_payload(*, alt_text, eyebrow, title, description, actions, hint):
    return {
        "type": "flex",
        "altText": alt_text,
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#FFF1EC",
                "paddingAll": "20px",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": eyebrow, "size": "xs", "weight": "bold", "color": "#9A3412"},
                    {"type": "text", "text": title, "size": "xl", "weight": "bold", "color": "#1E1B19"},
                    {"type": "text", "text": description, "size": "sm", "color": "#57423B", "wrap": True},
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#FFFDFC",
                "paddingAll": "16px",
                "spacing": "sm",
                "contents": [_navigation_button(*action) for action in actions],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#FFF8F6",
                "paddingAll": "16px",
                "contents": [
                    {"type": "text", "text": hint, "size": "xs", "color": "#74593F", "wrap": True}
                ],
            },
        },
    }


def _navigation_button(label, action_text, style):
    if action_text == "order_update":
        return {"type": "button", "style": style, "height": "sm",
                "action": {"type": "uri", "label": label, "uri": _order_update_liff_url()}}
    if action_text in ("ai_assistant", "其他問題"):
        ai_url = _ai_assistant_liff_url()
        if ai_url:
            return {
                "type": "button",
                "style": style,
                "height": "sm",
                "action": {
                    "type": "uri",
                    "label": label,
                    "uri": ai_url,
                },
            }
        return {
            "type": "button",
            "style": style,
            "height": "sm",
            "action": {"type": "message", "label": label, "text": "詢問其他問題"},
        }
    button = {
        "type": "button",
        "style": style,
        "height": "sm",
        "action": {"type": "message", "label": label, "text": action_text},
    }
    if style == "primary":
        button["color"] = "#E0683A"
    return button


def _answer_payload(outcome):
    sources = "；".join(
        f"{citation.source_identity}（v{citation.source_version}）"
        for citation in outcome.citations
    )
    return _text_payload(f"{outcome.text}\n\n資料來源：{sources}\n此資訊僅供說明，請以工會確認為準。")


def _clarification_payload(outcome):
    return {
        "type": "text",
        "text": "為了正確協助您，請選擇較接近的項目。",
        "quickReply": {
            "items": [
                {"type": "action", "action": {"type": "message", "label": option, "text": option}}
                for option in outcome.options
            ]
        },
    }


__all__ = ["LineServiceHelpApplication"]

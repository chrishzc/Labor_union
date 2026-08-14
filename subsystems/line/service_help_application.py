"""
File: service_help_application.py
Description: 將客服文字指令轉為可稽核的 LINE 回覆與長效 LIFF 登記入口。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
import os
from typing import Callable

from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identity_flow import LineIdentityFlowPurpose
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.customer_service.contracts import CreateCustomerServiceMessage
from subsystems.line.delivery_contracts import LineProviderOutcomeType
from subsystems.line.identity_contracts import OpenLineIdentityFlowCommand


_CATEGORY_ALIASES = {
    CustomerServiceCategory.SERVICE_FLOW: {"服務流程", "流程", "怎麼申請", "如何登記", "怎麼媒合", "1"},
    CustomerServiceCategory.PAYMENT_SUBSIDY: {"收費與補助", "收費", "費用", "價格", "補助", "政府補助", "要付多少", "2"},
    CustomerServiceCategory.SERVICE_PROGRESS: {"查詢服務進度", "查詢進度", "服務進度", "案件進度", "訂單進度", "目前狀態", "3"},
    CustomerServiceCategory.PROFILE_UPDATE: {"修改登記資料", "修改資料", "改資料", "電話錯誤", "地址錯誤", "日期要改", "4"},
    CustomerServiceCategory.CONTACT_UNION: {"聯絡工會人員", "聯絡工會", "找人", "找專員", "人工客服", "我要問人", "5"},
    CustomerServiceCategory.OTHER: {"其他問題", "其他", "不是以上", "問題", "詢問", "6"},
}


class LineServiceHelpApplication:
    def __init__(
        self,
        now: Callable[[], datetime],
        identity_url: Callable[[str, str], str] | None = None,
        reply_provider: object | None = None,
    ) -> None:
        self._now = now
        self._identity_url = identity_url
        self._reply_provider = reply_provider

    def handle(self, inbox, unit_of_work, line_user_id, text: str) -> bool:
        normalized = text.strip()
        if normalized == "服務登記":
            self._enqueue(
                inbox,
                unit_of_work,
                line_user_id,
                _text_payload(_registration_reply(_registration_liff_url())),
                "registration",
            )
            return True
        if normalized == "服務說明":
            self._reply_or_enqueue(inbox, unit_of_work, line_user_id, _service_menu_payload(), "menu")
            return True
        category = _category_for_text(normalized)
        if category is None:
            return False
        self._handle_category(inbox, unit_of_work, line_user_id, category, normalized)
        return True

    def _handle_category(self, inbox, unit_of_work, line_user_id, category, text):
        if category is CustomerServiceCategory.SERVICE_FLOW:
            payload = _text_payload(_SERVICE_FLOW_REPLY)
        elif category is CustomerServiceCategory.PAYMENT_SUBSIDY:
            payload = _text_payload(_PAYMENT_REPLY)
        elif category is CustomerServiceCategory.SERVICE_PROGRESS:
            payload = self._progress_payload(inbox, unit_of_work, line_user_id)
        else:
            ticket = unit_of_work.customer_service.create_or_append(
                CreateCustomerServiceMessage(line_user_id.value, category, text, _event_key(inbox, category.value))
            )
            payload = _text_payload(_TICKET_ACKNOWLEDGEMENTS[category])
            unit_of_work.audit.append(_ticket_audit(ticket.ticket_id, line_user_id.value))
        self._reply_or_enqueue(inbox, unit_of_work, line_user_id, payload, category.value)

    def _progress_payload(self, inbox, unit_of_work, line_user_id):
        context = unit_of_work.customer_service.latest_client_case(line_user_id.value)
        if context or self._identity_url is None:
            return _progress_payload(context)
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
        return _text_payload(_unbound_progress_reply(url))

    def _enqueue(self, inbox, unit_of_work, line_user_id, payload, suffix):
        event_id = inbox.event.event_id.value
        unit_of_work.delivery_tasks.enqueue(
            LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, line_user_id),
                LineMessageKind.FLEX if payload.get("type") == "flex" else LineMessageKind.TEXT,
                canonical_line_payload_json(payload), self._now(),
                IdempotencyKey(f"service-help:{suffix}:{event_id}"),
                CorrelationId(f"line-event:{event_id}"), "line_webhook_event", event_id,
            )
        )

    def _reply_or_enqueue(self, inbox, unit_of_work, line_user_id, payload, suffix):
        reply_token = _reply_token(inbox)
        if reply_token and self._reply_provider is not None:
            outcome = self._reply_provider.reply(reply_token, payload)
            if outcome.outcome_type is LineProviderOutcomeType.SUCCESS:
                unit_of_work.audit.append(
                    _reply_audit(
                        suffix,
                        line_user_id.value,
                        outcome.provider_message_id.value if outcome.provider_message_id else "",
                    )
                )
                return
            unit_of_work.audit.append(
                _reply_audit(suffix, line_user_id.value, outcome.error_code or "reply_failed")
            )
            return
        self._enqueue(inbox, unit_of_work, line_user_id, payload, suffix)


def _category_for_text(text):
    return next((category for category, aliases in _CATEGORY_ALIASES.items() if text in aliases), None)


def _event_key(inbox, suffix):
    return f"line-service-help:{suffix}:{inbox.event.event_id.value}"


def _ticket_audit(ticket_id, line_user_id):
    from subsystems.line.ports import LineAuditIntent
    return LineAuditIntent("customer_service.message.received", f"line:{line_user_id}", "customer_service_ticket", str(ticket_id))


def _reply_audit(suffix, line_user_id, provider_message_id):
    from subsystems.line.ports import LineAuditIntent
    return LineAuditIntent("line.webhook.reply.sent", f"line:{line_user_id}", "line_reply", f"{suffix}:{provider_message_id or 'accepted'}")


def _reply_token(inbox) -> str:
    try:
        payload = json.loads(inbox.event.payload_json)
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return ""
    token = payload.get("replyToken") if isinstance(payload, dict) else ""
    return token.strip() if isinstance(token, str) else ""


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
    return f"https://liff.line.me/{liff_id}?target=registration"


def _registration_reply(registration_url):
    if registration_url is None:
        return "服務登記入口尚未完成設定，請聯絡工會人員協助。"
    return f"請開啟以下服務登記頁面：\n\n{registration_url}"


def _service_menu_payload():
    cards = (
        ("服務流程", "了解登記、資料確認、月嫂媒合到簽約的完整流程。", "#1E3A8A"),
        ("收費與補助", "查看服務費用、樓層費與補助資格的初步說明。", "#0F766E"),
        ("查詢服務進度", "查詢已綁定案件的最新狀態與服務期間。", "#7C3AED"),
        ("修改登記資料", "申請修正姓名、電話、地址、日期等登記內容。", "#BE123C"),
        ("聯絡工會人員", "需要人工協助時，建立工會服務人員回覆需求。", "#B45309"),
        ("其他問題", "不是以上分類時，留下問題讓工會人員協助確認。", "#475569"),
    )
    return {
        "type": "flex",
        "altText": "請選擇服務說明項目",
        "contents": {
            "type": "carousel",
            "contents": [_service_help_card(*card) for card in cards],
        },
    }


def _service_help_card(label, description, color):
    return {
        "type": "bubble",
        "size": "micro",
        "hero": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": color,
            "height": "76px",
            "justifyContent": "center",
            "alignItems": "center",
            "contents": [
                {
                    "type": "text",
                    "text": label,
                    "weight": "bold",
                    "size": "lg",
                    "color": "#FFFFFF",
                    "align": "center",
                    "wrap": True,
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": description,
                    "size": "sm",
                    "color": "#334155",
                    "wrap": True,
                    "maxLines": 4,
                }
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": color,
                    "action": {
                        "type": "message",
                        "label": "選擇",
                        "text": label,
                    },
                }
            ],
        },
    }


_SERVICE_FLOW_REPLY = "服務流程如下：\n1. 完成服務登記。\n2. 工會確認資料與服務期程。\n3. 系統篩選可配合的月嫂。\n4. 月嫂同意接案後，工會提供資料給您確認。\n5. 雙方確認後，進入媒合與簽約流程。\n\n如您尚未登記，請點選下方「服務登記」。"
_PAYMENT_REPLY = "收費會依服務天數、每日時數、身分資格與樓層費計算。補助資格需由工會依您的登記資料確認；在資料確認完成前，系統僅提供初步說明，實際金額以工會確認結果為準。\n\n如您尚未登記，請先點選「服務登記」完成資料填寫。"
_TICKET_ACKNOWLEDGEMENTS = {
    CustomerServiceCategory.PROFILE_UPDATE: "已收到修改資料需求，工會人員確認後會聯絡您核對要修改的內容。",
    CustomerServiceCategory.CONTACT_UNION: "已收到聯絡需求，工會人員將盡快回覆。服務時間為週一至週五 09:00-18:00。",
    CustomerServiceCategory.OTHER: "已建立客服需求，工會人員將透過 LINE 與您確認問題內容。",
}


__all__ = ["LineServiceHelpApplication"]

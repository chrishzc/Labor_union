"""Canonical LINE service-help intent handler."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.customer_service.contracts import CreateCustomerServiceMessage


_CATEGORY_ALIASES = {
    CustomerServiceCategory.SERVICE_FLOW: {"服務流程", "流程", "怎麼申請", "如何登記", "怎麼媒合", "1"},
    CustomerServiceCategory.PAYMENT_SUBSIDY: {"收費與補助", "收費", "費用", "價格", "補助", "政府補助", "要付多少", "2"},
    CustomerServiceCategory.SERVICE_PROGRESS: {"查詢服務進度", "查詢進度", "服務進度", "案件進度", "目前狀態", "3"},
    CustomerServiceCategory.PROFILE_UPDATE: {"修改登記資料", "修改資料", "改資料", "電話錯誤", "地址錯誤", "日期要改", "4"},
    CustomerServiceCategory.CONTACT_UNION: {"聯絡工會人員", "聯絡工會", "找人", "找專員", "人工客服", "我要問人", "5"},
    CustomerServiceCategory.OTHER: {"其他問題", "其他", "不是以上", "問題", "詢問", "6"},
}


class LineServiceHelpApplication:
    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now

    def handle(self, inbox, unit_of_work, line_user_id, text: str) -> bool:
        normalized = text.strip()
        if normalized == "服務說明":
            self._enqueue(inbox, unit_of_work, line_user_id, _service_menu_payload(), "menu")
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
            payload = _progress_payload(unit_of_work.customer_service.latest_client_case(line_user_id.value))
        else:
            ticket = unit_of_work.customer_service.create_or_append(
                CreateCustomerServiceMessage(line_user_id.value, category, text, _event_key(inbox, category.value))
            )
            payload = _text_payload(_TICKET_ACKNOWLEDGEMENTS[category])
            unit_of_work.audit.append(_ticket_audit(ticket.ticket_id, line_user_id.value))
        self._enqueue(inbox, unit_of_work, line_user_id, payload, category.value)

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


def _category_for_text(text):
    return next((category for category, aliases in _CATEGORY_ALIASES.items() if text in aliases), None)


def _event_key(inbox, suffix):
    return f"line-service-help:{suffix}:{inbox.event.event_id.value}"


def _ticket_audit(ticket_id, line_user_id):
    from subsystems.line.ports import LineAuditIntent
    return LineAuditIntent("customer_service.message.received", f"line:{line_user_id}", "customer_service_ticket", str(ticket_id))


def _text_payload(text):
    return {"type": "text", "text": text}


def _progress_payload(context):
    if not context:
        return _text_payload("目前尚未找到您綁定的服務資料。請點選下方「服務登記」取得新的安全綁定入口。")
    dates = f"{context.get('start_date') or '未定'} 至 {context.get('end_date') or '未定'}"
    return _text_payload(f"最新案件：{context.get('case_no') or '尚未核發'}\n目前狀態：{context.get('status') or '資料確認中'}\n服務期間：{dates}")


def _service_menu_payload():
    labels = ("服務流程", "收費與補助", "查詢服務進度", "修改登記資料", "聯絡工會人員", "其他問題")
    buttons = [{"type": "button", "action": {"type": "message", "label": label, "text": label}, "style": "secondary", "height": "sm"} for label in labels]
    return {"type": "flex", "altText": "請選擇服務說明項目", "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [{"type": "text", "text": "服務說明", "weight": "bold", "size": "xl"}, {"type": "text", "text": "請選擇想了解或需要協助的項目", "wrap": True, "color": "#627D98"}, *buttons]}}}


_SERVICE_FLOW_REPLY = "服務流程如下：\n1. 完成服務登記。\n2. 工會確認資料與期程。\n3. 系統篩選可配合月嫂。\n4. 月嫂同意後提供資料確認。\n5. 雙方確認後進入媒合與簽約。"
_PAYMENT_REPLY = "收費會依服務天數、每日時數、身分資格與樓層費計算。補助資格與實際金額仍以工會完成資料確認後的結果為準。"
_TICKET_ACKNOWLEDGEMENTS = {
    CustomerServiceCategory.PROFILE_UPDATE: "已收到修改資料需求，工會人員確認後會聯絡您核對要修改的內容。",
    CustomerServiceCategory.CONTACT_UNION: "已收到聯絡需求，工會人員將盡快回覆。服務時間為週一至週五 09:00-18:00。",
    CustomerServiceCategory.OTHER: "已建立客服需求，工會人員將透過 LINE 與您確認問題內容。",
}


__all__ = ["LineServiceHelpApplication"]

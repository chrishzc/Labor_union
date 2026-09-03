"""
File: service_help_application.py
Description: 將客服文字路由為 durable LINE 回覆，並以同一 UoW 建立去敏 typed escalation。
"""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from typing import Callable

from domains.customer_service.ticket import CustomerServiceCategory
from domains.customer_service.escalation import EscalationContext, TriggerCode, evidence_digest
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identity_flow import LineIdentityFlowPurpose
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.customer_service.escalation_contracts import CreateHumanEscalation, HumanEscalationError
from subsystems.customer_service.contracts import CreateCustomerServiceMessage
from subsystems.line.identity_contracts import OpenLineIdentityFlowCommand
from subsystems.line.ports import LineAuditIntent
from subsystems.line.ai_router_contracts import (
    Clarification,
    DeterministicAnswer,
    DeterministicRoute,
    SafeMenu,
    TicketReferral,
    Unavailable,
)
from subsystems.line.deterministic_ai_router import DeterministicLineRouter
from subsystems.line.notification_policy import NotificationSourceEvent
from shared_kernel.identities import IdempotencyReceipt
from subsystems.line.runtime_human_escalation_source import normalize_complaint_text


_CATEGORY_ALIASES = {
    CustomerServiceCategory.SERVICE_FLOW: {"服務流程", "流程", "怎麼申請", "如何登記", "怎麼媒合", "1"},
    CustomerServiceCategory.PAYMENT_SUBSIDY: {"收費與補助", "收費", "費用", "價格", "補助", "政府補助", "要付多少", "2"},
    CustomerServiceCategory.SERVICE_PROGRESS: {"查詢服務進度", "查詢進度", "服務進度", "案件進度", "訂單進度", "目前狀態", "3"},
    CustomerServiceCategory.PROFILE_UPDATE: {"修改登記資料", "修改資料", "改資料", "電話錯誤", "地址錯誤", "日期要改", "4"},
    CustomerServiceCategory.OTHER: {"其他問題", "其他", "不是以上", "問題", "詢問", "聯絡工會人員", "聯絡工會", "找人", "找專員", "人工客服", "我要問人", "5", "6"},
}


class LineServiceHelpApplication:
    def __init__(
        self,
        now: Callable[[], datetime],
        identity_url: Callable[[str, str], str] | None = None,
        escalation_gateway=None,
    ) -> None:
        self._now = now
        self._identity_url = identity_url
        self._escalation_gateway = escalation_gateway
        self._router = DeterministicLineRouter()

    def handle(self, inbox, unit_of_work, line_user_id, text: str) -> bool:
        normalized = text.strip()
        complaint_context = normalize_complaint_text(normalized)
        if complaint_context is not None:
            self._create_complaint_escalation(
                inbox,
                unit_of_work,
                line_user_id,
                complaint_context,
            )
            return True
        if self._escalation_gateway is not None:
            self._escalation_gateway.hold_guard(_conversation_scope(line_user_id), unit_of_work)
        event_id = inbox.event.event_id.value
        outcome = self._router.route(normalized, source_event_id=event_id)
        if isinstance(outcome, TicketReferral):
            self._create_manual_ticket(inbox, unit_of_work, line_user_id, normalized, outcome)
            return True
        if isinstance(outcome, DeterministicRoute):
            if outcome.route_key == "registration":
                self._reply_or_enqueue(
                    inbox,
                    unit_of_work,
                    line_user_id,
                    _text_payload(_registration_reply(_registration_liff_url())),
                    "registration",
                    reason_code=outcome.reason_code,
                )
                return True
            if outcome.route_key == "service_help_menu":
                self._reply_or_enqueue(inbox, unit_of_work, line_user_id, _service_menu_payload(), "menu", reason_code=outcome.reason_code)
                return True
            if outcome.category is None:
                return False
            self._handle_category(inbox, unit_of_work, line_user_id, outcome.category, normalized)
            return True
        if isinstance(outcome, SafeMenu):
            # Unknown text belongs to the canonical Knowledge fallback owned by
            # the webhook composition. Consuming it here makes that durable
            # request path unreachable.
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

    def apply_manual_fallback(self, inbox, unit_of_work, line_user_id, text: str) -> int:
        """Create the typed manual fallback selected by the development preview."""
        event_id = inbox.event.event_id.value
        event_key = f"line-service-help:other:{event_id}"
        existing_lookup = getattr(unit_of_work.customer_service, "get_by_event_key", None)
        if callable(existing_lookup):
            existing = existing_lookup(event_key)
            if existing is not None:
                return int(existing.ticket_id)
        referral = TicketReferral(
            CustomerServiceCategory.OTHER,
            "explicit_human_request",
            event_id,
            IdempotencyKey(f"line-service-help:other:{event_id}"),
        )
        return self._create_manual_ticket(inbox, unit_of_work, line_user_id, text, referral)

    def _create_complaint_escalation(
        self,
        inbox,
        unit_of_work,
        line_user_id,
        context,
    ) -> None:
        """Route complaint language through the M4 ingress in the caller UoW.

        The source normalizer intentionally returns no complaint text.  The
        Customer Service owner still receives its required routing identity,
        while the ticket note, escalation command, and alert carry only the
        closed canonical context; the source fingerprint proves that the original
        ingress was observed without retaining the raw complaint message.
        """
        if self._escalation_gateway is None:
            raise HumanEscalationError(
                "unavailable",
                "human_escalation_ingress_unavailable",
                "客訴轉真人流程尚未配置，已安全停止。",
                retryable=True,
            )
        event_id = inbox.event.event_id.value
        event_key = f"line-complaint:{event_id}"
        ticket = unit_of_work.customer_service.create_or_append(
            CreateCustomerServiceMessage(
                line_user_id.value,
                CustomerServiceCategory.OTHER,
                "客訴訊息已遮罩；請查看客服 escalation 的去敏摘要。",
                event_key,
            )
        )
        command = CreateHumanEscalation(
            source_event_identity=event_key,
            source_kind="line_inbox",
            source_fingerprint=evidence_digest(
                {
                    "event_identity": event_id,
                    "line_user_id": line_user_id.value,
                    "context": context,
                }
            ),
            trigger_code=TriggerCode.COMPLAINT,
            trigger_policy_version=context["policy_version"],
            ticket_category=CustomerServiceCategory.OTHER,
            context=EscalationContext.from_mapping(context),
            hold_scope=_conversation_scope(line_user_id),
            idempotency_key=IdempotencyKey(
                f"line-complaint-escalation:{event_id}"
            ),
            correlation_id=CorrelationId(f"line-event:{event_id}"),
            actor=ActorContext("system:line-complaint-ingress"),
        )
        receipt = self._escalation_gateway.create_for_ticket(command, ticket, unit_of_work)
        # A redelivered complaint is already represented by the canonical
        # escalation receipt.  Do not append another audit event or enqueue a
        # second empathy task; the delivery repository remains the final
        # idempotency boundary for callers that cannot return a receipt.
        if getattr(receipt, "replayed", False):
            return
        unit_of_work.audit.append(_ticket_audit(ticket.ticket_id, line_user_id.value))
        self._reply_or_enqueue(
            inbox,
            unit_of_work,
            line_user_id,
            _text_payload(
                "很抱歉讓您有不好的感受，我們已暫停自動回覆，客服專員會盡快協助您。"
            ),
            "complaint-empathy",
        )

    def _create_manual_ticket(self, inbox, unit_of_work, line_user_id, text, referral):
        ticket = unit_of_work.customer_service.create_or_append(
            CreateCustomerServiceMessage(
                line_user_id.value,
                referral.category,
                text,
                referral.idempotency_key.value,
            )
        )
        if self._escalation_gateway is not None:
            command = _escalation_command(inbox, line_user_id, referral)
            self._escalation_gateway.create_for_ticket(command, ticket, unit_of_work)
        unit_of_work.audit.append(_ticket_audit(ticket.ticket_id, line_user_id.value))
        self._reply_or_enqueue(
            inbox,
            unit_of_work,
            line_user_id,
            _text_payload(_TICKET_ACKNOWLEDGEMENTS[referral.category]),
            "ticket",
        )
        return int(ticket.ticket_id)

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

    def _enqueue(self, inbox, unit_of_work, line_user_id, payload, suffix, *, reason_code=None):
        event_id = inbox.event.event_id.value
        request = LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, line_user_id),
                LineMessageKind.FLEX if payload.get("type") == "flex" else LineMessageKind.TEXT,
                canonical_line_payload_json(payload), self._now(),
                IdempotencyKey(f"service-help:{suffix}:{event_id}"),
                CorrelationId(f"line-event:{event_id}"), "line_webhook_event", event_id,
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

def _event_key(inbox, suffix):
    return f"line-service-help:{suffix}:{inbox.event.event_id.value}"


def _ticket_audit(ticket_id, line_user_id):
    return LineAuditIntent("customer_service.message.received", f"line:{line_user_id}", "customer_service_ticket", str(ticket_id))


def _conversation_scope(line_user_id):
    return evidence_digest({"conversation_kind": "line_user", "conversation_identity": line_user_id.value})


def _escalation_command(inbox, line_user_id, referral):
    triggers = {
        "explicit_human_request": TriggerCode.EXPLICIT_HUMAN_REQUEST,
        "answer_rejected": TriggerCode.EXPLICIT_WRONG_ANSWER,
    }
    trigger = triggers.get(referral.reason_code)
    if trigger is None:
        raise HumanEscalationError(
            "domain_blocked",
            "human_escalation_source_invalid",
            "LINE referral reason 無法建立 escalation",
        )
    source_event_identity = referral.idempotency_key.value
    policy_version = "m2-deterministic.v1"
    source_kind = "ticket_referral"
    source_fingerprint = evidence_digest(
        {
            "source_event_identity": source_event_identity,
            "source_kind": source_kind,
            "trigger_code": trigger.value,
            "policy_version": policy_version,
            "category": referral.category.value,
        }
    )
    source_event_id = inbox.event.event_id.value
    return CreateHumanEscalation(
        source_event_identity=source_event_identity,
        source_kind=source_kind,
        source_fingerprint=source_fingerprint,
        trigger_code=trigger,
        trigger_policy_version=policy_version,
        ticket_category=referral.category,
        context=EscalationContext(
            summary_code=trigger.value,
            policy_version=policy_version,
            category=referral.category.value,
            redaction_version="m4-mask.v1",
        ),
        hold_scope=_conversation_scope(line_user_id),
        idempotency_key=IdempotencyKey(f"line-escalation:{evidence_digest(source_event_identity)}"),
        correlation_id=CorrelationId(f"line-event:{source_event_id}"),
        actor=ActorContext("system:line-service-help"),
    )


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


def _service_menu_payload():
    cards = (
        ("服務流程", "了解登記、資料確認、月嫂媒合到簽約的完整流程。", "#1E3A8A"),
        ("收費與補助", "查看服務費用、樓層費與補助資格的初步說明。", "#0F766E"),
        ("查詢服務進度", "查詢已綁定案件的最新狀態與服務期間。", "#7C3AED"),
        ("修改登記資料", "申請修正姓名、電話、地址、日期等登記內容。", "#BE123C"),
        ("月嫂身分認證", "月嫂本人可送出身分確認申請，由工會人員審核。", "#B45309", "我是月嫂"),
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


def _service_help_card(label, description, color, action_text=None):
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
                        "text": action_text or label,
                    },
                }
            ],
        },
    }


_SERVICE_FLOW_REPLY = "服務流程如下：\n1. 完成服務登記。\n2. 工會確認資料與服務期程。\n3. 系統篩選可配合的月嫂。\n4. 月嫂同意接案後，工會提供資料給您確認。\n5. 雙方確認後，進入媒合與簽約流程。\n\n如您尚未登記，請點選下方「服務登記」。"
_PAYMENT_REPLY = "收費會依服務天數、每日時數、身分資格與樓層費計算。補助資格需由工會依您的登記資料確認；在資料確認完成前，系統僅提供初步說明，實際金額以工會確認結果為準。\n\n如您尚未登記，請先點選「服務登記」完成資料填寫。"
_TICKET_ACKNOWLEDGEMENTS = {
    CustomerServiceCategory.PROFILE_UPDATE: "已收到修改資料需求，工會人員確認後會聯絡您核對要修改的內容。",
    CustomerServiceCategory.OTHER: "已建立客服需求，工會人員將透過 LINE 與您確認問題內容。",
}


def _safe_menu_payload(outcome):
    return {
        "type": "text",
        "text": "請選擇服務說明項目；若問題未列出，請選擇「聯絡工會人員」。",
        "quickReply": {
            "items": [
                {"type": "action", "action": {"type": "message", "label": option, "text": option}}
                for option in outcome.options
            ]
        },
    }


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

"""
File: service_help_application.py
Description: 將已核准的自助服務文字入口路由為 LINE 回覆。
"""

from __future__ import annotations

from subsystems.line.message_copy_catalog import configured_payload
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.navigation_catalog import FAQ_MENU_COMMAND, SERVICE_PROGRESS_COMMAND, route_aliases

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Callable

from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.knowledge_retrieval.qa_catalog import line_faq_reply_fits
from domains.line.faq_chat_layout import FAQ_ID_PATTERN, FaqCardView, FaqCategory, faq_short_label
from domains.line.legacy_faq import LEGACY_FAQ_CATEGORIES, LEGACY_FAQ_POLICY_LABELS
from domains.line.identities import LineSourceType
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.knowledge_retrieval.faq_catalog import (
    KnowledgeCatalogUnavailable,
    PublishedFaq,
    PublishedFaqCatalog,
    is_faq_id,
)
from subsystems.line.faq_chat_layout import (
    FaqCategoryNotPublished,
    FaqChatLayoutApplication,
    FaqLayoutUnavailable,
)
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
from subsystems.line.predecessor_line_faq import PredecessorLineFaq
from subsystems.line.runtime_human_escalation_source import normalize_complaint_text


_FAQ_PREFIX = "faq:v1:"
_FAQ_PAGE_SIZE = 6
_FAQ_NOT_FOUND = "這個問答目前無法讀取。請返回常見問題，或直接在此聊天室留言。"
RETIRED_AI_GUIDANCE_TEXT = f"此功能已停用。請在本聊天室輸入「{FAQ_MENU_COMMAND}」，或直接留言由工會人員協助。"
_FAQ_UNAVAILABLE = "常見問答暫時無法使用。請稍後再試，或直接在此聊天室留言。"

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
    "menu", "order-update-menu", "clarification", "unavailable",
    "retired-ai-action", "service_flow", "payment_subsidy", "service_progress", "profile-update-form", "other",
    "knowledge", "category_faq", "faq-guidance",
})


def _normalized_resume_command(text: str) -> str:
    return "".join(text.split()).casefold()


@dataclass(frozen=True, slots=True)
class ServiceHelpFaqReaders:
    catalog: PublishedFaqCatalog | None
    layout: FaqChatLayoutApplication | None
    predecessor: PredecessorLineFaq | None = None


class LineServiceHelpApplication:
    def __init__(
        self,
        now: Callable[[], datetime],
        *,
        faq_catalog: PublishedFaqCatalog | None = None,
        faq_layout: FaqChatLayoutApplication | None = None,
        faq_reader: Callable[[], ServiceHelpFaqReaders] | None = None,
    ) -> None:
        self._now = now
        self._faq_reader = faq_reader or (lambda: ServiceHelpFaqReaders(faq_catalog, faq_layout))
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
        if normalized in LEGACY_FAQ_POLICY_LABELS:
            return self._handle_faq_text(inbox, unit_of_work, line_user_id, normalized)
        event_id = inbox.event.event_id.value
        outcome = self._router.route(normalized, source_event_id=event_id)
        if reply_only and isinstance(outcome, DeterministicAnswer):
            return False
        if isinstance(outcome, DeterministicRoute):
            if outcome.route_key == "service_help_menu":
                return self._handle_faq_action(inbox, unit_of_work, line_user_id, "menu", "0")
            if outcome.route_key == "ai_assistant_menu":
                if not _same_private_chat(inbox, line_user_id):
                    return False
                self._retired_ai_action(inbox, unit_of_work, line_user_id)
                return True
            if outcome.route_key in {"order_update_menu", "order_update_request"}:
                self._reply_or_enqueue(inbox, unit_of_work, line_user_id, _order_update_menu_payload(), "order-update-menu", reason_code=outcome.reason_code)
                return True
            if outcome.category is None:
                return False
            return self._handle_category(inbox, unit_of_work, line_user_id, outcome.category)
        if self._handle_faq_text(inbox, unit_of_work, line_user_id, normalized):
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
        if postback_data.startswith("faq:"):
            action, _, value = postback_data.removeprefix(_FAQ_PREFIX).partition(":")
            return self._handle_faq_action(inbox, unit_of_work, line_user_id, action, value)
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
            _text_payload(RETIRED_AI_GUIDANCE_TEXT),
            "retired-ai-action",
            reason_code="chat_ai_retired",
        )

    def _handle_category(self, inbox, unit_of_work, line_user_id, category) -> bool:
        if category in {CustomerServiceCategory.SERVICE_FLOW, CustomerServiceCategory.PAYMENT_SUBSIDY}:
            return self._handle_faq_action(inbox, unit_of_work, line_user_id, "category", category.value)
        if category is CustomerServiceCategory.SERVICE_PROGRESS:
            payload = self._progress_payload(unit_of_work, line_user_id)
        elif category is CustomerServiceCategory.PROFILE_UPDATE:
            payload = _profile_update_payload()
        else:
            return self._handle_faq_action(inbox, unit_of_work, line_user_id, "menu", "0")
        suffix = "profile-update-form" if category is CustomerServiceCategory.PROFILE_UPDATE else category.value
        self._reply_or_enqueue(inbox, unit_of_work, line_user_id, payload, suffix)
        return True

    def _handle_faq_text(self, inbox, unit_of_work, line_user_id, text: str) -> bool:
        if not text or not _same_private_chat(inbox, line_user_id):
            return False
        predecessor = None
        try:
            readers = self._faq_reader()
            catalog, predecessor = readers.catalog, readers.predecessor
            if catalog is None:
                return False
            if predecessor is not None:
                matches = predecessor.match_text(text)
                if matches is None:
                    if text in LEGACY_FAQ_POLICY_LABELS:
                        payload = _predecessor_category_payload(predecessor, "payment_subsidy")
                        self._reply_or_enqueue(inbox, unit_of_work, line_user_id, payload, "category_faq")
                        return True
                    return False
            else:
                matches = catalog.match_legacy_text(text)
                if matches is None:
                    matches = catalog.match_alias(text)
                    if not matches and text not in LEGACY_FAQ_POLICY_LABELS:
                        return False
                elif len(matches) == 1 and any(
                    item.qa_id != matches[0].qa_id for item in catalog.match_alias(text)
                ):
                    matches = ()
        except KnowledgeCatalogUnavailable:
            self._faq_guidance(inbox, unit_of_work, line_user_id, unavailable=True, predecessor=predecessor is not None)
            return True
        if len(matches) != 1:
            self._faq_guidance(inbox, unit_of_work, line_user_id, predecessor=predecessor is not None)
            return True
        self._reply_or_enqueue(
            inbox, unit_of_work, line_user_id, _qa_answer_payload(matches[0]),
            "knowledge", reason_code="catalog_match",
        )
        return True

    def _handle_faq_action(self, inbox, unit_of_work, line_user_id, action: str, value: str) -> bool:
        if not _same_private_chat(inbox, line_user_id):
            return False
        predecessor = None
        try:
            readers = self._faq_reader()
            catalog, layout, predecessor = readers.catalog, readers.layout, readers.predecessor
            if predecessor is not None:
                if action == "menu":
                    payload, suffix = _service_menu_payload(), "menu"
                elif action == "category" and value in LEGACY_FAQ_CATEGORIES:
                    payload, suffix = _predecessor_category_payload(predecessor, value), "category_faq"
                else:
                    raise FaqCategoryNotPublished()
            elif action == "menu":
                if layout is None:
                    raise FaqLayoutUnavailable()
                published = layout.published_layout()
                categories = published.categories if published else ()
                page = int(value) if re.fullmatch(r"[0-9]{1,9}", value) else 0
                payload, suffix = _published_menu_payload(unit_of_work, categories, page), "menu"
            elif action == "category" and re.fullmatch(FAQ_ID_PATTERN, value):
                if layout is None:
                    raise FaqLayoutUnavailable()
                preview = layout.preview_published(value)
                payload, suffix = _category_card_payload(preview.view), "category_faq"
            elif action == "question" and is_faq_id(value):
                if catalog is None:
                    raise KnowledgeCatalogUnavailable()
                question = catalog.get(value)
                if question is None:
                    raise FaqCategoryNotPublished()
                payload, suffix = _qa_answer_payload(question), "knowledge"
            else:
                raise FaqCategoryNotPublished()
        except FaqCategoryNotPublished:
            self._faq_guidance(inbox, unit_of_work, line_user_id, predecessor=predecessor is not None)
            return True
        except (FaqLayoutUnavailable, KnowledgeCatalogUnavailable):
            self._faq_guidance(inbox, unit_of_work, line_user_id, unavailable=True, predecessor=predecessor is not None)
            return True
        self._reply_or_enqueue(inbox, unit_of_work, line_user_id, payload, suffix)
        return True

    def _faq_guidance(self, inbox, unit_of_work, line_user_id, *, unavailable: bool = False, predecessor: bool = False) -> None:
        payload = _text_payload(_FAQ_UNAVAILABLE if unavailable else _FAQ_NOT_FOUND)
        payload["quickReply"] = {
            "items": [
                *_faq_back_quick_reply(predecessor=predecessor)["items"],
                *_fixed_service_quick_actions(),
            ],
        }
        self._reply_or_enqueue(
            inbox, unit_of_work, line_user_id, payload, "faq-guidance",
            reason_code="faq_source_unavailable" if unavailable else "faq_not_available",
        )

    def _progress_payload(self, unit_of_work, line_user_id):
        context = unit_of_work.customer_service.latest_client_case(line_user_id.value)
        if not context:
            return configured_payload(unit_of_work, "service-progress-unbound", _progress_payload(context))
        return configured_payload(unit_of_work, "service-progress", _progress_payload(context), {
            "case_no": context.get("case_no") or "尚未核發", "status": context.get("status") or "資料確認中",
            "start_date": context.get("start_date") or "未定", "end_date": context.get("end_date") or "未定"})

    def _enqueue(self, inbox, unit_of_work, line_user_id, payload, suffix, *, reason_code=None):
        event_id = inbox.event.event_id.value
        same_private_chat = _same_private_chat(inbox, line_user_id)
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

def _same_private_chat(inbox, line_user_id) -> bool:
    source = getattr(inbox.event, "source", None)
    return (
        line_user_id is not None
        and getattr(source, "source_type", None) is LineSourceType.USER
        and getattr(source, "user_id", None) == line_user_id
    )


def _text_payload(text):
    return {"type": "text", "text": text}


def _progress_payload(context):
    if not context:
        return _text_payload(_unbound_progress_reply())
    dates = f"{context.get('start_date') or '未定'} 至 {context.get('end_date') or '未定'}"
    return _text_payload(f"最新案件：{context.get('case_no') or '尚未核發'}\n目前狀態：{context.get('status') or '資料確認中'}\n服務期間：{dates}")


def _unbound_progress_reply() -> str:
    return "目前尚未找到您綁定的服務資料。請從訪客圖文選單點選「預約與登記」。"


def _registration_reply(registration_url):
    if registration_url is None:
        return "服務登記入口尚未完成設定，請聯絡工會人員協助。"
    return f"請開啟以下服務登記頁面：\n\n{registration_url}"


def _fixed_service_quick_actions():
    return [
        {"type": "action", "action": {"type": "message", "label": label, "text": text}}
        for label, text in (
            ("查詢進度", SERVICE_PROGRESS_COMMAND),
            ("修改資料", "修改登記資料"),
        )
    ]


def _common_category_quick_replies() -> dict[str, object]:
    return {"items": [
        {"type": "action", "action": {"type": "message", "label": label, "text": text}}
        for label, text in (
            ("📋 服務流程", "常見問題：服務流程"),
            ("💰 費用補助", "常見問題：收費與補助"),
        )
    ] + _fixed_service_quick_actions()}


def _service_menu_payload(quick_reply=None):
    actions = (
        ("📋 服務流程與申請", "常見問題：服務流程", "secondary"),
        ("💰 費用收費與政府補助", "常見問題：收費與補助", "secondary"),
        ("🔍 如何查詢目前服務進度？", SERVICE_PROGRESS_COMMAND, "secondary"),
        ("✏️ 登記資料填錯怎麼辦？", "修改登記資料", "secondary"),
    )
    return _navigation_card_payload(
        alt_text="新竹市月子工會：常見問題與服務說明",
        eyebrow="新竹市月子工會",
        title="常見問題與服務說明",
        description="整理家長最常詢問的服務重點與其他問題，點選下方分類查看常見問題。",
        actions=actions,
        hint="點選問題分類可展開常見題目；找不到答案時，請直接在聊天室留言。",
        quick_reply=quick_reply or _common_category_quick_replies(),
    )


def _faq_action(kind, value, label):
    return {"type": "postback", "label": label, "data": f"{_FAQ_PREFIX}{kind}:{value}"}


def _quick_faq_action(action):
    return {"type": "action", "action": {**action, "label": faq_short_label(action["label"], 20)}}


def _faq_back_quick_reply(*, predecessor=False):
    if predecessor:
        return {"items": [
            {"type": "action", "action": {"type": "message", "label": "返回常見問題", "text": FAQ_MENU_COMMAND}}
        ]}
    return {"items": [_quick_faq_action(_faq_action("menu", 0, "返回常見問題"))]}


def _published_menu_payload(unit_of_work, categories: tuple[FaqCategory, ...], page: int):
    if page * _FAQ_PAGE_SIZE >= len(categories):
        page = 0
    start = page * _FAQ_PAGE_SIZE
    actions = [
        _faq_action("category", category.category_id, category.name)
        for category in categories[start:start + _FAQ_PAGE_SIZE]
    ]
    if page > 0:
        actions.append(_faq_action("menu", page - 1, "上一頁"))
    if start + _FAQ_PAGE_SIZE < len(categories):
        actions.append(_faq_action("menu", page + 1, "下一頁"))

    payload = configured_payload(unit_of_work, "service-menu", _service_menu_payload())
    body = payload["contents"]["body"]["contents"]
    body[:] = [_flex_action_button(action) for action in actions] + body[2:]
    quick_items = [_quick_faq_action(action) for action in actions]
    payload["quickReply"]["items"] = quick_items + _fixed_service_quick_actions()
    if not categories:
        payload["contents"]["header"]["contents"][2]["text"] = "目前尚無已發布的常見問答分類。您可使用下方入口或直接留言。"
    return payload



def _predecessor_category_payload(reader: PredecessorLineFaq, category_id: str):
    name, title, description, _ = LEGACY_FAQ_CATEGORIES[category_id]
    actions = [
        (faq_short_label(question, 18), question, "secondary")
        for question in reader.card_questions(category_id)
    ]
    return _navigation_card_payload(
        alt_text=f"新竹市月子工會：{title}",
        eyebrow="新竹市月子工會 · 常見問題",
        title=title,
        description=description,
        actions=actions,
        hint="點選問題即可在對話中查看解答。",
        quick_reply={"items": [
            *_faq_back_quick_reply(predecessor=True)["items"],
            *(item for item in _common_category_quick_replies()["items"]
              if name not in item["action"]["text"]),
        ]},
    )


def _category_card_payload(view: FaqCardView):
    actions = [
        _faq_action("question", button.qa_id, button.label)
        for button in view.buttons
    ]
    quick_items = [_quick_faq_action(action) for action in actions]
    quick_items.extend(_faq_back_quick_reply()["items"])
    payload = _navigation_card_payload(
        alt_text=f"新竹市月子工會：{view.title}",
        eyebrow="新竹市月子工會 · 常見問題",
        title=view.title,
        description=view.description,
        actions=(),
        hint="點選題目即可查看解答。" if actions else _FAQ_NOT_FOUND,
        quick_reply={"items": quick_items},
    )
    if actions:
        payload["contents"]["body"]["contents"] = [_flex_action_button(action) for action in actions]
    else:
        payload["contents"].pop("body")
    return payload


def _flex_action_button(action):
    return {"type": "button", "style": "secondary", "height": "sm", "action": action}


def _qa_answer_payload(item: PublishedFaq) -> dict[str, str]:
    if not line_faq_reply_fits(item.answer):
        return _text_payload("這則常見問答目前無法完整顯示。如需解答，請直接在此留言。")
    return _text_payload(item.answer)


def _profile_update_payload():
    return _text_payload("如需修改聯絡電話、服務地址或個人登記資料，請直接在此聊天室留言，工會專員將由後台為您即時調整與確認。")


def _order_update_menu_payload():
    return _text_payload("如需變更服務時段、服務天數或訂單內容，請直接在此聊天室留言，工會專員將由後台為您即時確認與調整。")


def _navigation_card_payload(*, alt_text, eyebrow, title, description, actions, hint, quick_reply=None):
    payload = {
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
                    *([{"type": "text", "text": description, "size": "sm", "color": "#57423B", "wrap": True}] if description else []),
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
    if quick_reply:
        payload["quickReply"] = quick_reply
    return payload


def _navigation_button(label, action_text, style):
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

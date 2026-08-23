"""
File: deterministic_ai_router.py
Description: 以固定優先序完成 M2 路由；不連 DB、不呼叫 provider、不執行 mutation。
"""

from __future__ import annotations

from domains.customer_service.ticket import CustomerServiceCategory
from domains.knowledge_retrieval.knowledge import KnowledgeAnswer
from shared_kernel.identities import IdempotencyKey
from shared_kernel.validation import require_canonical_text
from subsystems.line.ai_router_contracts import (
    Clarification,
    DeterministicAnswer,
    DeterministicRoute,
    RouterOutcome,
    SafeMenu,
    TicketReferral,
    Unavailable,
)


_HUMAN_MARKERS = (
    "人工",
    "客服",
    "聯絡工會",
    "找人",
    "找專員",
    "問人",
    "答錯",
    "不對",
    "無法解決",
)
_IDENTITY_ALIASES = {
    "綁定訂單": ("customer_binding", "customer_binding"),
    "訂單查詢": ("customer_binding", "customer_binding"),
    "綁定後台帳號": ("admin_binding", "admin_binding"),
}
_GROUP_INTENTS = {
    "工會選單": "union_menu",
    "開啟客服系統": "union_menu",
    "月嫂驗證管理": "union_menu",
}
_SERVICE_ALIASES = {
    "服務登記": (None, "registration"),
    "服務說明": (None, "service_help_menu"),
    "服務流程": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "流程": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "怎麼申請": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "如何登記": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "怎麼媒合": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "1": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "收費與補助": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "收費": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "費用": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "價格": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "補助": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "政府補助": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "要付多少": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "2": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "查詢服務進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "查詢進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "服務進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "案件進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "訂單進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "目前狀態": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "3": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "修改登記資料": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "修改資料": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "改資料": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "電話錯誤": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "地址錯誤": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "日期要改": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "4": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "其他問題": (CustomerServiceCategory.OTHER, "other"),
    "其他": (CustomerServiceCategory.OTHER, "other"),
    "不是以上": (CustomerServiceCategory.OTHER, "other"),
    "問題": (CustomerServiceCategory.OTHER, "other"),
    "詢問": (CustomerServiceCategory.OTHER, "other"),
    "5": (CustomerServiceCategory.OTHER, "other"),
    "6": (CustomerServiceCategory.OTHER, "other"),
}
_SAFE_MENU_OPTIONS = ("服務說明", "服務登記", "聯絡工會人員")
_CLARIFICATION_OPTIONS = ("服務說明", "聯絡工會人員")


class DeterministicLineRouter:
    """Pure M2 Phase 1 classifier with a closed, provider-free result set."""

    def route(
        self,
        text: str,
        *,
        source_event_id: str,
        score: int | None = None,
        knowledge_answer: KnowledgeAnswer | None = None,
        knowledge_index_ready: bool | None = None,
    ) -> RouterOutcome:
        normalized = text.strip() if isinstance(text, str) else ""
        require_canonical_text(source_event_id, "source event id", 191)

        human_reason = _human_reason(normalized)
        if human_reason is not None:
            return TicketReferral(
                CustomerServiceCategory.OTHER,
                human_reason,
                source_event_id,
                IdempotencyKey(f"line-service-help:other:{source_event_id}"),
            )

        identity = _IDENTITY_ALIASES.get(normalized)
        if identity is not None:
            route_key, flow_id = identity
            return DeterministicRoute(route_key, None, flow_id, "protected_identity_alias")

        group_route = _GROUP_INTENTS.get(normalized)
        if group_route is not None:
            return DeterministicRoute(group_route, None, None, "approved_group_intent")

        service = _SERVICE_ALIASES.get(normalized)
        if service is not None:
            category, route_key = service
            return DeterministicRoute(route_key, category, None, "approved_service_help_alias")

        if knowledge_answer is not None:
            if knowledge_index_ready is False:
                return _safe_menu("knowledge_index_unavailable")
            return DeterministicAnswer(
                "published_knowledge",
                knowledge_answer.answer,
                knowledge_answer.citations,
                knowledge_answer.index_version,
                authoritative=knowledge_answer.authoritative,
            )
        if knowledge_index_ready is False:
            return _safe_menu("knowledge_index_unavailable")

        band = score_band(score)
        if band == "50_79":
            return Clarification("service_help_clarification", _CLARIFICATION_OPTIONS, "ambiguous_intent")
        if band == "gte_80":
            return Unavailable("deterministic_answer_unavailable", False, "請轉交客服人員確認。")
        return _safe_menu("unknown_intent")


def score_band(score: int | None) -> str:
    if score is None:
        return "lt_50"
    if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 100:
        raise ValueError("router score must be an integer between 0 and 100")
    if score >= 80:
        return "gte_80"
    if score >= 50:
        return "50_79"
    return "lt_50"


def _human_reason(text: str) -> str | None:
    if not text:
        return "empty_input"
    if any(marker in text for marker in ("答錯", "不對", "無法解決")):
        return "answer_rejected"
    if any(marker in text for marker in _HUMAN_MARKERS):
        return "explicit_human_request"
    return None


def _safe_menu(reason_code: str) -> SafeMenu:
    return SafeMenu("service_help_safe_menu", _SAFE_MENU_OPTIONS, reason_code)


__all__ = ["DeterministicLineRouter", "score_band"]

"""
File: deterministic_ai_router.py
Description: 以固定優先序完成 M2 路由；不連 DB、不呼叫 provider、不執行 mutation。
"""

from __future__ import annotations

from domains.customer_service.ticket import CustomerServiceCategory
from domains.knowledge_retrieval.knowledge import KnowledgeAnswer
from shared_kernel.validation import require_canonical_text
from subsystems.line.ai_router_contracts import (
    Clarification,
    DeterministicAnswer,
    DeterministicRoute,
    RouterOutcome,
    SafeMenu,
    Unavailable,
)
from subsystems.line.navigation_catalog import (
    CATALOG_REVISION,
    CATALOG_SOURCE_IDENTITY,
    entry_for_alias,
)


_IDENTITY_ALIASES = {"綁定訂單", "訂單查詢", "綁定後台帳號"}
_GROUP_INTENTS = {"工會選單", "開啟客服系統", "月嫂驗證管理"}
_SERVICE_ALIASES = {
    "服務登記": (None, "registration"),
    "服務說明": (None, "service_help_menu"),
    "服務與問答": (None, "service_help_menu"),
    "常見問答": (None, "service_help_menu"),
    "常見問題": (None, "service_help_menu"),
    "常用問題": (None, "service_help_menu"),
    "問答": (None, "service_help_menu"),
    "FAQ": (None, "service_help_menu"),
    "常見問題：服務流程": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "常見問題：收費與補助": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "常見問題：費用與補助": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "常見問題：查詢進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "常見問題：修改資料": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "常見問題：月嫂媒合": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "常見問題：餐飲服務": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "常見問題：請假代班": (CustomerServiceCategory.SERVICE_FLOW, "service_flow"),
    "AI客服": (None, "ai_assistant_menu"),
    "AI問答": (None, "ai_assistant_menu"),
    "AI智慧問答": (None, "ai_assistant_menu"),
    "修改訂單資訊": (None, "order_update_menu"),
    "改訂單內容": (None, "order_update_menu"),
    "修改服務地址": (CustomerServiceCategory.OTHER, "order_update_request"),
    "修改下廚需求": (CustomerServiceCategory.OTHER, "order_update_request"),
    "修改服務天數": (CustomerServiceCategory.OTHER, "order_update_request"),
    "修改每日服務時段": (CustomerServiceCategory.OTHER, "order_update_request"),
    "其他訂單內容": (CustomerServiceCategory.OTHER, "order_update_request"),
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
    "一般市民（最高40小時）": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "補助市民（最高120小時）": (CustomerServiceCategory.PAYMENT_SUBSIDY, "payment_subsidy"),
    "查詢服務進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "查詢進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "服務進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "案件進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "訂單進度": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "目前狀態": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "3": (CustomerServiceCategory.SERVICE_PROGRESS, "service_progress"),
    "修改登記資料": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "改個人資料": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "修改資料": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "改資料": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "電話錯誤": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "地址錯誤": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "4": (CustomerServiceCategory.PROFILE_UPDATE, "profile_update"),
    "其他問題": (None, "service_help_menu"),
    "詢問其他問題": (None, "service_help_menu"),
    "其他": (None, "service_help_menu"),
    "不是以上": (None, "service_help_menu"),
    "問題": (None, "service_help_menu"),
    "詢問": (None, "service_help_menu"),
    "5": (None, "service_help_menu"),
    "6": (None, "service_help_menu"),
}
_SAFE_MENU_OPTIONS = ("服務與問答", "服務登記")
_CLARIFICATION_OPTIONS = ("服務與問答", "服務登記")
_SUBSIDY_SCOPE_CLARIFICATION_OPTIONS = (
    "一般市民（最高40小時）",
    "補助市民（最高120小時）",
)

_ROUTE_CATEGORY_MAP: dict[str, CustomerServiceCategory | None] = {
    "registration": None,
    "service_help_menu": None,
    "order_update_menu": None,
    "order_update_request": CustomerServiceCategory.OTHER,
    "service_flow": CustomerServiceCategory.SERVICE_FLOW,
    "payment_subsidy": CustomerServiceCategory.PAYMENT_SUBSIDY,
    "service_progress": CustomerServiceCategory.SERVICE_PROGRESS,
    "profile_update": CustomerServiceCategory.PROFILE_UPDATE,
    "other": None,
    "group_helper_menu": None,
}


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

        if _is_ambiguous_subsidy_scope(normalized):
            return Clarification(
                "subsidy_scope",
                _SUBSIDY_SCOPE_CLARIFICATION_OPTIONS,
                "subsidy_scope_ambiguous",
            )

        entry = entry_for_alias(normalized)
        if entry is not None:
            if entry.tier == "identity":
                return DeterministicRoute(
                    entry.route_key, None, entry.route_key, "protected_identity_alias",
                    entry.source_identity, entry.revision, entry.source_identity,
                    "protected_route", 100,
                )
            if entry.tier == "admin":
                return DeterministicRoute(
                    entry.route_key, None, None, "approved_group_intent",
                    entry.source_identity, entry.revision, entry.source_identity,
                    "protected_route", 100,
                )
            if entry.tier == "navigation":
                category = _ROUTE_CATEGORY_MAP.get(entry.route_key)
                route_key = "service_help_menu" if entry.route_key == "other" else entry.route_key
                return DeterministicRoute(
                    route_key, category, None, "approved_service_help_alias",
                    entry.source_identity, entry.revision, entry.source_identity,
                    "navigation", 100,
                )

        if normalized in _IDENTITY_ALIASES and entry is not None:
            return DeterministicRoute(
                entry.route_key, None, entry.route_key, "protected_identity_alias",
                entry.source_identity, entry.revision, entry.source_identity,
                "protected_route", 100,
            )

        if normalized in _GROUP_INTENTS and entry is not None:
            return DeterministicRoute(
                entry.route_key, None, None, "approved_group_intent",
                entry.source_identity, entry.revision, entry.source_identity,
                "protected_route", 100,
            )

        service = _SERVICE_ALIASES.get(normalized)
        if service is not None:
            category, route_key = service
            return DeterministicRoute(
                route_key, category, None, "approved_service_help_alias",
                CATALOG_SOURCE_IDENTITY, CATALOG_REVISION, CATALOG_SOURCE_IDENTITY,
                "navigation", 100,
            )

        if knowledge_answer is not None:
            if knowledge_index_ready is False:
                return _safe_menu("knowledge_index_unavailable")
            return DeterministicAnswer(
                "published_knowledge",
                knowledge_answer.answer,
                knowledge_answer.citations,
                knowledge_answer.index_version,
                authoritative=knowledge_answer.authoritative,
                source_identity=CATALOG_SOURCE_IDENTITY,
                source_revision=knowledge_answer.index_version,
                semantic_bucket="answer",
                confidence=100,
            )
        if knowledge_index_ready is False:
            return _safe_menu("knowledge_index_unavailable")

        band = score_band(score)
        if band == "50_79":
            return Clarification(
                "service_help_clarification", _CLARIFICATION_OPTIONS, "ambiguous_intent",
                "50_79", CATALOG_SOURCE_IDENTITY, CATALOG_REVISION, score or 50,
            )
        if band == "gte_80":
            return Unavailable(
                "deterministic_answer_unavailable", False, "如需協助，請直接在 LINE 官方帳號聊天室留言。",
                CATALOG_SOURCE_IDENTITY, CATALOG_REVISION, "manual_fallback",
            )
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


def _is_ambiguous_subsidy_scope(text: str) -> bool:
    compact = "".join(text.split())
    if "補助" not in compact:
        return False
    if any(scope in compact for scope in ("社福", "低收入", "中低收入", "低收", "中低收")):
        return False
    if any(scope in compact for scope in ("市府", "市民", "一般市民", "一般產婦")):
        return False
    requested_fact = (
        "多少",
        "金額",
        "幾元",
        "時數",
        "幾小時",
        "小時",
        "資格",
        "符合",
        "可以申請",
        "能申請",
    )
    return any(marker in compact for marker in requested_fact)


def _safe_menu(reason_code: str) -> SafeMenu:
    return SafeMenu("service_help_safe_menu", _SAFE_MENU_OPTIONS, reason_code)


__all__ = ["DeterministicLineRouter", "score_band"]

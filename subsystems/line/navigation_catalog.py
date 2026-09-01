"""Closed, server-owned LINE M2 navigation and semantic catalog."""

from __future__ import annotations

from dataclasses import dataclass


CATALOG_REVISION = 1
CATALOG_SOURCE_IDENTITY = "LU96-M2-ROUTER-REPLY-SOURCE-V1"


@dataclass(frozen=True, slots=True)
class LineNavigationEntry:
    alias: str
    route_key: str
    tier: str
    public_route: str | None
    postback_identity: str | None
    source_identity: str = CATALOG_SOURCE_IDENTITY
    revision: int = CATALOG_REVISION


@dataclass(frozen=True, slots=True)
class LineNavigationReplyReadback:
    """Server-owned deterministic reply identity exposed to the local workbench."""

    source_response_id: str
    source_event_id: str
    reply_kind: str
    reason_code: str
    source_identity: str
    source_revision: int


_ENTRIES = (
    LineNavigationEntry("綁定訂單", "customer_binding", "identity", "/line-identity", None),
    LineNavigationEntry("訂單查詢", "customer_binding", "identity", "/line-identity", None),
    LineNavigationEntry("綁定後台帳號", "admin_binding", "identity", "/line-identity", None),
    LineNavigationEntry("工會選單", "union_menu", "admin", "/line-mobile-admin", "line:admin-menu"),
    LineNavigationEntry("開啟客服系統", "union_menu", "admin", "/line-mobile-admin?target=customer_service", "line:customer-service"),
    LineNavigationEntry("月嫂驗證管理", "union_menu", "admin", "/line-mobile-admin?target=staff_review", "line:staff-review"),
    LineNavigationEntry("服務登記", "registration", "navigation", "/line-identity", None),
    LineNavigationEntry("服務說明", "service_help_menu", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("服務流程", "service_flow", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("流程", "service_flow", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("怎麼申請", "service_flow", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("如何登記", "service_flow", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("怎麼媒合", "service_flow", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("收費與補助", "payment_subsidy", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("收費", "payment_subsidy", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("費用", "payment_subsidy", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("價格", "payment_subsidy", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("補助", "payment_subsidy", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("政府補助", "payment_subsidy", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("要付多少", "payment_subsidy", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("查詢服務進度", "service_progress", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("查詢進度", "service_progress", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("服務進度", "service_progress", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("案件進度", "service_progress", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("訂單進度", "service_progress", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("目前狀態", "service_progress", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("修改登記資料", "profile_update", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("修改資料", "profile_update", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("改資料", "profile_update", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("電話錯誤", "profile_update", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("地址錯誤", "profile_update", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("日期要改", "profile_update", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("其他問題", "other", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("其他", "other", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("不是以上", "other", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("問題", "other", "navigation", "/line-mobile-admin?target=customer_service", None),
    LineNavigationEntry("詢問", "other", "navigation", "/line-mobile-admin?target=customer_service", None),
)


def catalog_entries() -> tuple[LineNavigationEntry, ...]:
    return _ENTRIES


def entry_for_alias(alias: str) -> LineNavigationEntry | None:
    return next((entry for entry in _ENTRIES if entry.alias == alias), None)


__all__ = [
    "CATALOG_REVISION",
    "CATALOG_SOURCE_IDENTITY",
    "LineNavigationEntry",
    "LineNavigationReplyReadback",
    "catalog_entries",
    "entry_for_alias",
]

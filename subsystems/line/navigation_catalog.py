"""
File: navigation_catalog.py
Description: LINE 導覽與意圖目錄，提供確定性引導動作、自訂觸發指令持久化與別名查詢。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


CATALOG_REVISION = 1
CATALOG_SOURCE_IDENTITY = "LU96-M2-ROUTER-REPLY-SOURCE-V1"
CATALOG_STORAGE_PATH = (
    Path(__file__).resolve().parents[2] / "document" / "line" / "AI客服引導動作別名.json"
)


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


_ROUTE_METADATA: dict[str, dict[str, str | None]] = {
    "customer_binding": {
        "tier": "identity",
        "public_route": "/line-identity",
        "postback_identity": None,
    },
    "admin_binding": {
        "tier": "identity",
        "public_route": "/line-identity",
        "postback_identity": None,
    },
    "union_menu": {
        "tier": "admin",
        "public_route": "/line-mobile-admin",
        "postback_identity": "line:admin-menu",
    },
    "registration": {
        "tier": "navigation",
        "public_route": "/line-identity",
        "postback_identity": None,
    },
    "service_help_menu": {
        "tier": "navigation",
        "public_route": "/line-mobile-admin?target=customer_service",
        "postback_identity": None,
    },
    "order_update_menu": {
        "tier": "navigation",
        "public_route": "/line-order-update",
        "postback_identity": None,
    },
    "order_update_request": {
        "tier": "navigation",
        "public_route": "/line-mobile-admin?target=customer_service",
        "postback_identity": None,
    },
    "service_flow": {
        "tier": "navigation",
        "public_route": "/line-mobile-admin?target=customer_service",
        "postback_identity": None,
    },
    "payment_subsidy": {
        "tier": "navigation",
        "public_route": "/line-mobile-admin?target=customer_service",
        "postback_identity": None,
    },
    "service_progress": {
        "tier": "navigation",
        "public_route": "/line-mobile-admin?target=customer_service",
        "postback_identity": None,
    },
    "profile_update": {
        "tier": "navigation",
        "public_route": "/line-mobile-admin?target=customer_service",
        "postback_identity": None,
    },
    "other": {
        "tier": "navigation",
        "public_route": "/line-mobile-admin?target=customer_service",
        "postback_identity": None,
    },
}

_BASE_ALIASES: dict[str, list[str]] = {
    "customer_binding": ["綁定訂單", "訂單查詢"],
    "admin_binding": ["綁定後台帳號"],
    "union_menu": [
        "工會選單",
        "開啟客服系統",
        "開啟待辦工作台",
        "開啟異常中心",
        "開啟營運摘要",
    ],
    "registration": ["服務登記"],
    "service_help_menu": ["服務說明", "服務與問答", "常見問答", "問答", "FAQ"],
    "order_update_menu": ["修改訂單資訊"],
    "order_update_request": [
        "修改服務地址",
        "修改下廚需求",
        "修改服務天數",
        "修改每日服務時段",
        "其他訂單內容",
    ],
    "service_flow": ["服務流程", "流程", "怎麼申請", "如何登記", "怎麼媒合"],
    "payment_subsidy": [
        "收費與補助",
        "收費",
        "費用",
        "價格",
        "補助",
        "政府補助",
        "要付多少",
    ],
    "service_progress": [
        "查詢服務進度",
        "查詢進度",
        "服務進度",
        "案件進度",
        "訂單進度",
        "目前狀態",
    ],
    "profile_update": ["修改登記資料", "修改資料", "改資料", "電話錯誤", "地址錯誤"],
    "other": ["其他問題", "其他", "不是以上", "問題", "詢問"],
}


def load_persisted_aliases(
    path: Path | None = None,
) -> tuple[int, dict[str, list[str]]]:
    file_path = path or CATALOG_STORAGE_PATH
    if not file_path.exists():
        return CATALOG_REVISION, {k: list(v) for k, v in _BASE_ALIASES.items()}
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            revision = int(data.get("revision", CATALOG_REVISION))
            routes = data.get("routes", {})
            result: dict[str, list[str]] = {}
            for k, default_aliases in _BASE_ALIASES.items():
                if k in routes and isinstance(routes[k], list):
                    cleaned = [str(a).strip() for a in routes[k] if str(a).strip()]
                    result[k] = cleaned if cleaned else list(default_aliases)
                else:
                    result[k] = list(default_aliases)
            return revision, result
    except (OSError, ValueError, TypeError):
        return CATALOG_REVISION, {k: list(v) for k, v in _BASE_ALIASES.items()}


def save_persisted_aliases(
    revision: int,
    routes: dict[str, list[str]],
    path: Path | None = None,
) -> None:
    file_path = path or CATALOG_STORAGE_PATH
    temp_path = file_path.with_suffix(".json.tmp")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "revision": revision,
        "routes": routes,
    }
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    temp_path.replace(file_path)


_cached_catalog: tuple[int, tuple[LineNavigationEntry, ...]] | None = None


def _invalidate_cache() -> None:
    global _cached_catalog
    _cached_catalog = None


def catalog_entries(path: Path | None = None) -> tuple[LineNavigationEntry, ...]:
    global _cached_catalog
    if path is None and _cached_catalog is not None:
        return _cached_catalog[1]

    revision, routes = load_persisted_aliases(path)
    entries: list[LineNavigationEntry] = []
    for route_key, meta in _ROUTE_METADATA.items():
        aliases = routes.get(route_key, _BASE_ALIASES.get(route_key, []))
        for alias in aliases:
            entries.append(
                LineNavigationEntry(
                    alias=alias,
                    route_key=route_key,
                    tier=meta["tier"] or "navigation",
                    public_route=meta["public_route"],
                    postback_identity=meta["postback_identity"],
                    source_identity=CATALOG_SOURCE_IDENTITY,
                    revision=revision,
                )
            )
    result = tuple(entries)
    if path is None:
        _cached_catalog = (revision, result)
    return result


def get_current_revision(path: Path | None = None) -> int:
    global _cached_catalog
    if path is None and _cached_catalog is not None:
        return _cached_catalog[0]
    rev, _ = load_persisted_aliases(path)
    return rev


def entry_for_alias(
    alias: str, path: Path | None = None
) -> LineNavigationEntry | None:
    return next(
        (entry for entry in catalog_entries(path) if entry.alias == alias), None
    )


def update_route_aliases(
    route_key: str,
    aliases: list[str],
    path: Path | None = None,
) -> tuple[int, tuple[LineNavigationEntry, ...]]:
    if route_key not in _ROUTE_METADATA:
        raise KeyError(f"route_key_not_found:{route_key}")

    cleaned: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        s = str(alias).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)

    if not cleaned:
        raise ValueError("aliases_cannot_be_empty")

    revision, current_routes = load_persisted_aliases(path)
    for other_route, other_aliases in current_routes.items():
        if other_route == route_key:
            continue
        collision = set(cleaned).intersection(set(other_aliases))
        if collision:
            colliding = next(iter(collision))
            raise ValueError(f"alias_conflict:{colliding}_already_belongs_to_{other_route}")

    current_routes[route_key] = cleaned
    new_revision = revision + 1
    save_persisted_aliases(new_revision, current_routes, path)
    _invalidate_cache()
    return new_revision, catalog_entries(path)


def reset_route_aliases(
    route_key: str | None = None,
    path: Path | None = None,
) -> tuple[int, tuple[LineNavigationEntry, ...]]:
    revision, current_routes = load_persisted_aliases(path)
    if route_key:
        if route_key not in _ROUTE_METADATA:
            raise KeyError(f"route_key_not_found:{route_key}")
        current_routes[route_key] = list(_BASE_ALIASES[route_key])
    else:
        current_routes = {k: list(v) for k, v in _BASE_ALIASES.items()}
    new_revision = revision + 1
    save_persisted_aliases(new_revision, current_routes, path)
    _invalidate_cache()
    return new_revision, catalog_entries(path)


__all__ = [
    "CATALOG_REVISION",
    "CATALOG_SOURCE_IDENTITY",
    "CATALOG_STORAGE_PATH",
    "LineNavigationEntry",
    "LineNavigationReplyReadback",
    "catalog_entries",
    "entry_for_alias",
    "get_current_revision",
    "load_persisted_aliases",
    "reset_route_aliases",
    "save_persisted_aliases",
    "update_route_aliases",
]

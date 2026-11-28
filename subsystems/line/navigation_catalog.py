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
FAQ_MENU_COMMAND = "常見問題"
SERVICE_PROGRESS_COMMAND = "查詢服務進度"
GROUP_POSTPONEMENT_COMMAND = "雙方合意延期"
_FIXED_ROUTE_COMMANDS = {
    "service_help_menu": FAQ_MENU_COMMAND,
    "service_progress": SERVICE_PROGRESS_COMMAND,
    "group_postponement": GROUP_POSTPONEMENT_COMMAND,
}
_RESERVED_COMMANDS = frozenset(_FIXED_ROUTE_COMMANDS.values())
_RETIRED_UNION_SWITCH_ALIASES = frozenset({"工會選單", "切換工會", "工會客服"})


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
    "order_group_bind": {
        "tier": "admin",
        "public_route": None,
        "postback_identity": "line:order-group-bind",
    },
    "order_group_invite": {
        "tier": "admin",
        "public_route": None,
        "postback_identity": "line:order-group-invite",
    },
    "service_help_menu": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": None,
    },
    "order_update_menu": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": None,
    },
    "order_update_request": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": None,
    },
    "service_flow": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": None,
    },
    "payment_subsidy": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": None,
    },
    "service_progress": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": None,
    },
    "profile_update": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": None,
    },
    "resume_ai_assistant": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": "customer-service:handoff:resume-ai",
    },
    "feedback_resolved": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": None,
    },
    "feedback_unresolved": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": None,
    },
    "group_helper_menu": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": "line:group-helper-menu",
    },
    "group_postponement": {
        "tier": "navigation",
        "public_route": None,
        "postback_identity": "line:group-postponement",
    },
}

_BASE_ALIASES: dict[str, list[str]] = {
    "admin_binding": ["綁定後台帳號", "綁定工會帳號", "綁定system_admin"],
    "union_menu": [
        "開啟客服系統",
        "開啟待辦工作台",
        "開啟異常中心",
        "開啟營運摘要",
    ],
    "order_group_bind": ["綁定群組", "綁定案件群組", "綁定訂單"],
    "order_group_invite": ["發送邀請"],
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
    "profile_update": ["修改登記資料", "修改資料", "改資料", "電話錯誤", "地址錯誤"],
    "resume_ai_assistant": [
        "恢復AI助理",
        "恢復AI",
        "繼續使用AI",
        "恢復機器人",
        "恢復機器人回答",
        "繼續讓機器人回答",
    ],
    "feedback_resolved": ["有幫助", "👍 有幫助", "很有幫助", "有解決"],
    "feedback_unresolved": ["未解決", "👎 未解決", "沒解決", "沒有幫助", "未解決（通報專人客服）"],
    "group_helper_menu": ["小幫手", "工會", "月嫂選單", "服務選單"],
    **{route: [command] for route, command in _FIXED_ROUTE_COMMANDS.items()},
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
                if k not in _FIXED_ROUTE_COMMANDS and k in routes and isinstance(routes[k], list):
                    excluded = _RESERVED_COMMANDS
                    if k == "union_menu":
                        excluded |= _RETIRED_UNION_SWITCH_ALIASES
                    cleaned = [alias for raw in routes[k] if (alias := str(raw).strip()) and alias not in excluded]
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


def route_aliases(route_key: str, path: Path | None = None) -> tuple[str, ...]:
    """Return configured aliases for one route key, falling back to its defaults."""
    _, routes = load_persisted_aliases(path)
    return tuple(routes.get(route_key) or _BASE_ALIASES.get(route_key, ()))


def _require_editable_route(route_key: str) -> None:
    if route_key not in _ROUTE_METADATA:
        raise KeyError(f"route_key_not_found:{route_key}")
    if route_key in _FIXED_ROUTE_COMMANDS:
        raise ValueError("route_aliases_fixed")


def update_route_aliases(
    route_key: str,
    aliases: list[str],
    path: Path | None = None,
) -> tuple[int, tuple[LineNavigationEntry, ...]]:
    _require_editable_route(route_key)

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
    if route_key == "union_menu" and _RETIRED_UNION_SWITCH_ALIASES.intersection(cleaned):
        raise ValueError("retired_menu_switch_alias")

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
        _require_editable_route(route_key)
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
    "FAQ_MENU_COMMAND",
    "GROUP_POSTPONEMENT_COMMAND",
    "SERVICE_PROGRESS_COMMAND",
    "LineNavigationEntry",
    "LineNavigationReplyReadback",
    "catalog_entries",
    "entry_for_alias",
    "get_current_revision",
    "load_persisted_aliases",
    "reset_route_aliases",
    "route_aliases",
    "save_persisted_aliases",
    "update_route_aliases",
]

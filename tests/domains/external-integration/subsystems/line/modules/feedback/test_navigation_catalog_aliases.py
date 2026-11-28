"""
File: test_navigation_catalog_aliases.py
Description: 測試 LINE 導覽目錄的觸發指令更新、持久化與確定性路由器動態別名解析。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_line_configuration_reader
from api.routes.line_ai_events import router as ai_events_router
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.ai_router_contracts import DeterministicRoute
from subsystems.line.deterministic_ai_router import DeterministicLineRouter
from subsystems.line.navigation_catalog import (
    catalog_entries,
    entry_for_alias,
    load_persisted_aliases,
    reset_route_aliases,
    update_route_aliases,
)


def test_custom_navigation_aliases_lifecycle(tmp_path: Path):
    storage_file = tmp_path / "custom_aliases.json"

    # 1. Base load
    rev, routes = load_persisted_aliases(storage_file)
    assert rev >= 1
    assert "profile_update" in routes
    initial_profile_aliases = list(routes["profile_update"])

    # 2. Update aliases for profile_update
    new_aliases = initial_profile_aliases + ["我要換地址", "手機號碼填錯"]
    new_rev, entries = update_route_aliases("profile_update", new_aliases, path=storage_file)
    assert new_rev == rev + 1

    # Verify entry_for_alias finds the new alias
    entry = entry_for_alias("我要換地址", path=storage_file)
    assert entry is not None
    assert entry.route_key == "profile_update"
    assert entry.tier == "navigation"

    # 3. Collision rejection
    with pytest.raises(ValueError, match="alias_conflict"):
        update_route_aliases("service_flow", ["我要換地址"], path=storage_file)

    # 4. Empty rejection
    with pytest.raises(ValueError, match="aliases_cannot_be_empty"):
        update_route_aliases("profile_update", ["   "], path=storage_file)

    # 5. Reset route
    reset_rev, reset_entries = reset_route_aliases("profile_update", path=storage_file)
    assert reset_rev == new_rev + 1
    rev_after, routes_after = load_persisted_aliases(storage_file)
    assert "我要換地址" not in routes_after["profile_update"]


def test_navigation_catalog_api_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_storage = tmp_path / "api_test_aliases.json"
    test_storage.write_text(json.dumps({
        "revision": 3,
        "routes": {
            "staff_binding": ["我是月嫂", "自訂月嫂入口"],
            "registration": ["服務登記", "自訂登記入口"],
            "customer_binding": ["綁定訂單", "自訂客戶入口"],
            "service_help_menu": ["服務說明", "自訂問答入口"],
            "service_progress": ["訂單進度", "自訂進度入口"],
            "group_postponement": ["合意延期", "自訂延期入口"],
            "other": ["其他問題", "自訂其他入口"],
            "admin_binding": ["常見問題", "查詢服務進度", "雙方合意延期"],
            "menu_switch_help": ["切換選單", "自訂切換指引"],
            "menu_switch_customer": ["客戶選單", "自訂客戶選單"],
            "menu_switch_visitor": ["訪客選單", "回主選單"],
            "menu_switch_staff": ["月嫂專區", "自訂月嫂選單"],
            "union_menu": ["工會選單", "切換工會", "工會客服", "開啟客服系統"],
        },
    }), encoding="utf-8")
    import subsystems.line.navigation_catalog as nav_module
    monkeypatch.setattr(nav_module, "CATALOG_STORAGE_PATH", test_storage)
    monkeypatch.setattr(nav_module, "_cached_catalog", None)

    app = FastAPI()
    app.include_router(ai_events_router)
    app.dependency_overrides[require_line_configuration_reader] = lambda: AdminPrincipal(
        id=1,
        username="admin",
        display_name="Admin",
        role="admin",
        capabilities=frozenset({"line.configuration.manage", "line.configuration.read"}),
    )
    client = TestClient(app)

    # GET catalog
    get_res = client.get("/api/v1/line/ai-events/catalog")
    assert get_res.status_code == 200
    catalog = get_res.json()["data"]
    assert len(catalog["entries"]) > 0
    active_routes = {entry["route_key"] for entry in catalog["entries"]}
    retired_routes = {
        "staff_binding", "registration", "customer_binding", "other",
        "menu_switch_help", "menu_switch_customer", "menu_switch_visitor", "menu_switch_staff",
    }
    assert retired_routes.isdisjoint(active_routes)
    for alias in (
        "我是月嫂", "服務登記", "自訂月嫂入口", "自訂登記入口", "自訂客戶入口",
        "切換選單", "自訂切換指引", "客戶選單", "自訂客戶選單", "訪客選單", "回主選單",
        "月嫂專區", "自訂月嫂選單", "工會選單", "切換工會", "工會客服",
    ):
        assert not isinstance(DeterministicLineRouter().route(alias, source_event_id="retired-alias"), DeterministicRoute)
    assert [entry["alias"] for entry in catalog["entries"] if entry["route_key"] == "union_menu"] == ["開啟客服系統"]
    admin_entry = entry_for_alias("開啟客服系統", path=test_storage)
    assert admin_entry is not None
    assert admin_entry.public_route == "/line-mobile-admin"
    assert admin_entry.postback_identity == "line:admin-menu"
    assert entry_for_alias("綁定訂單", path=test_storage).route_key == "order_group_bind"
    for route in retired_routes:
        assert client.put(f"/api/v1/line/ai-events/catalog/{route}/aliases", json={"aliases": ["新別名"]}).status_code == 404
        assert client.post(f"/api/v1/line/ai-events/catalog/{route}/reset").status_code == 404
    original_storage = test_storage.read_bytes()
    for route, command in {
        "service_help_menu": "常見問題",
        "service_progress": "查詢服務進度",
        "group_postponement": "雙方合意延期",
    }.items():
        assert [entry["alias"] for entry in catalog["entries"] if entry["route_key"] == route] == [command]
        assert entry_for_alias(command, path=test_storage).route_key == route
        put_fixed = client.put(f"/api/v1/line/ai-events/catalog/{route}/aliases", json={"aliases": [command, "新別名"]})
        reset_fixed = client.post(f"/api/v1/line/ai-events/catalog/{route}/reset")
        assert put_fixed.status_code == reset_fixed.status_code == 400
        assert put_fixed.json()["detail"] == reset_fixed.json()["detail"] == "route_aliases_fixed"
    assert entry_for_alias("綁定後台帳號", path=test_storage).route_key == "admin_binding"
    for alias in ("自訂問答入口", "自訂進度入口", "自訂延期入口", "自訂其他入口"):
        assert entry_for_alias(alias, path=test_storage) is None
    collision = client.put("/api/v1/line/ai-events/catalog/admin_binding/aliases", json={"aliases": ["常見問題"]})
    assert collision.status_code == 400
    assert collision.json()["detail"] == "alias_conflict:常見問題_already_belongs_to_service_help_menu"
    retired = client.put("/api/v1/line/ai-events/catalog/union_menu/aliases", json={"aliases": ["工會選單"]})
    assert retired.status_code == 400
    assert retired.json()["detail"] == "retired_menu_switch_alias"
    assert test_storage.read_bytes() == original_storage

    # PUT aliases
    put_res = client.put(
        "/api/v1/line/ai-events/catalog/profile_update/aliases",
        json={"aliases": ["修改登記資料", "自訂測試換電話"]},
    )
    assert put_res.status_code == 200
    assert "已成功更新" in put_res.json()["message"]

    # Router should route the new alias
    router = DeterministicLineRouter()
    outcome = router.route("自訂測試換電話", source_event_id="test-event-custom")
    assert isinstance(outcome, DeterministicRoute)
    assert outcome.route_key == "profile_update"

    # Reset aliases
    reset_res = client.post("/api/v1/line/ai-events/catalog/profile_update/reset")
    assert reset_res.status_code == 200
    assert "已將「profile_update」的觸發指令恢復預設" in reset_res.json()["message"]


def test_group_helper_keeps_aliases_and_retires_staff_assistance_close(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_storage = tmp_path / "helper_aliases.json"
    import subsystems.line.navigation_catalog as nav_module
    monkeypatch.setattr(nav_module, "CATALOG_STORAGE_PATH", test_storage)
    nav_module._invalidate_cache()

    _, routes = load_persisted_aliases(test_storage)
    assert "group_helper_menu" in routes
    assert "staff_assistance_close" not in routes
    assert "小幫手" in routes["group_helper_menu"]
    assert "工會" in routes["group_helper_menu"]

    router = DeterministicLineRouter()
    helper_outcome = router.route("小幫手", source_event_id="helper-menu-wake")
    assert isinstance(helper_outcome, DeterministicRoute)
    assert helper_outcome.route_key == "group_helper_menu"

    close_outcome = router.route("已處理結案", source_event_id="staff-close-cmd")
    assert not isinstance(close_outcome, DeterministicRoute)


def test_all_chatroom_commands_in_catalog_and_dynamic_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_storage = tmp_path / "all_commands_aliases.json"
    import subsystems.line.navigation_catalog as nav_module
    monkeypatch.setattr(nav_module, "CATALOG_STORAGE_PATH", test_storage)
    nav_module._invalidate_cache()

    rev, routes = load_persisted_aliases(test_storage)
    expected_keys = {
        "admin_binding",
        "union_menu",
        "order_group_bind",
        "order_group_invite",
        "group_helper_menu",
        "group_postponement",
        "resume_ai_assistant",
        "feedback_resolved",
        "feedback_unresolved",
    }
    assert expected_keys.issubset(set(routes))
    assert "human_handoff" not in routes
    assert entry_for_alias("呼叫專員", path=test_storage) is None
    new_rev, _ = update_route_aliases("order_group_bind", ["綁定群組", "綁定訂單", "群組開案"], path=test_storage)
    assert new_rev == rev + 1
    assert entry_for_alias("綁定訂單", path=test_storage).route_key == "order_group_bind"
    assert entry_for_alias("群組開案", path=test_storage).route_key == "order_group_bind"

    from subsystems.line.order_group_application import _group_command_aliases, _parse_binding
    from subsystems.line.group_helper_application import _match_postponement_text

    bind_aliases, invite_aliases = _group_command_aliases()
    assert "群組開案" in bind_aliases
    assert "發送邀請" in invite_aliases
    assert _parse_binding("群組開案 115000104 https://line.me/R/ti/g/abc", bind_aliases) == (
        "115000104",
        "https://line.me/R/ti/g/abc",
    )

    with pytest.raises(ValueError, match="route_aliases_fixed"):
        update_route_aliases("group_postponement", ["雙方合意延期", "順延日期"], path=test_storage)
    assert _match_postponement_text("雙方合意延期：2026-12-01 順延至 2026-12-10") is not None
    assert _match_postponement_text("順延日期：2026-12-01 順延至 2026-12-10") is None

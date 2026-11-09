"""
File: test_navigation_catalog_aliases.py
Description: 測試 LINE 導覽目錄的觸發指令更新、持久化與確定性路由器動態別名解析。
"""

from __future__ import annotations

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
    import subsystems.line.navigation_catalog as nav_module
    monkeypatch.setattr(nav_module, "CATALOG_STORAGE_PATH", test_storage)
    nav_module._invalidate_cache()

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

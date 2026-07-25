"""
================================================================================
檔案名稱: tests/test_data_browser_admin_route.py
功能說明: 驗證 Data Browser Admin Router 的認證授權與 PATCH 觸發參數
================================================================================
"""

import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.schemas.data_browser import DataBrowserPatchRequest
from api.routes import data_browser_admin
from services import data_browser_admin_schema_service


def test_admin_auth_dependency_rejects_unauthenticated():
    with pytest.raises(HTTPException) as error:
        data_browser_admin.admin_auth_dependency(None)

    assert error.value.status_code == 401
    assert error.value.detail == "unauthenticated"


def test_admin_router_get_without_auth_context_returns_401():
    admin_app = FastAPI()
    admin_app.include_router(data_browser_admin.router)
    client = TestClient(admin_app)
    response = client.get("/api/v1/admin/data-browser/orders")

    assert response.status_code == 401
    assert response.json()["detail"] == "unauthenticated"


def test_admin_auth_dependency_rejects_non_admin():
    with pytest.raises(HTTPException) as error:
        data_browser_admin.admin_auth_dependency("user_role")

    assert error.value.status_code == 403
    assert error.value.detail == "forbidden"


def test_admin_auth_dependency_allows_admin_role():
    assert data_browser_admin.admin_auth_dependency("admin_role") == "admin_role"


def test_patch_data_browser_row_passes_authenticated_operator_to_service(monkeypatch):
    captured = {}

    def _fake_patch(
        table_name: str,
        row_id: str,
        updates: dict,
        operator_id: str = "admin_ui",
    ) -> bool:
        captured.update(
            table=table_name,
            row_id=row_id,
            operator=operator_id,
            updates=updates,
        )
        return True

    monkeypatch.setattr(data_browser_admin_schema_service, "patch_data_browser_table_row", _fake_patch)

    response = data_browser_admin.patch_data_browser_row(
        DataBrowserPatchRequest(updates={"service_days": 10}),
        table="orders",
        row_id_str="TEST_ROUTE_001",
        auth_context="admin_role",
    )

    assert response.data is True
    assert captured["operator"] == "admin_role"


def test_patch_data_browser_row_validation_error_maps_to_422(monkeypatch):
    def _fake_patch(*_args, **_kwargs):
        raise ValueError("欄位 [bad] 不在可編輯白名單中，更新已取消。")

    monkeypatch.setattr(data_browser_admin_schema_service, "patch_data_browser_table_row", _fake_patch)

    with pytest.raises(HTTPException) as error:
        data_browser_admin.patch_data_browser_row(
            DataBrowserPatchRequest(updates={"bad": "x"}),
            table="orders",
            row_id_str="TEST_ROUTE_001",
            auth_context="admin_role",
        )

    assert error.value.status_code == 422


def test_patch_data_browser_row_not_found_maps_to_404(monkeypatch):
    def _fake_patch(*_args, **_kwargs):
        raise ValueError("指定資料列不存在或欄位變更未生效，更新已取消。")

    monkeypatch.setattr(data_browser_admin_schema_service, "patch_data_browser_table_row", _fake_patch)

    with pytest.raises(HTTPException) as error:
        data_browser_admin.patch_data_browser_row(
            DataBrowserPatchRequest(updates={"service_days": 99}),
            table="orders",
            row_id_str="TEST_ROUTE_MISS",
            auth_context="admin_role",
        )

    assert error.value.status_code == 404

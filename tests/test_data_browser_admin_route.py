"""Data Browser routes must reuse the formal administrator dependency."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies import admin_auth
from api.routes import data_browser_admin
from api.schemas.data_browser import DataBrowserSourceCorrectionPreviewRequest
from subsystems.access.authentication_session import AdminPrincipal


def _principal(role: str = "system_admin") -> AdminPrincipal:
    return AdminPrincipal(7, "verified-admin", "Verified Admin", role)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(data_browser_admin.router)
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer session-token",
    }


def test_admin_router_get_without_session_returns_401(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")

    response = _client().get("/api/v1/admin/data-browser/orders")

    assert response.status_code == 401
    assert response.json()["detail"] == "缺少有效的管理員 Session"


def test_admin_router_rejects_insufficient_formal_role(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setattr(admin_auth, "get_admin_session", lambda _token: _principal("line_manager"))

    response = _client().get(
        "/api/v1/admin/data-browser/orders",
        headers=_headers(),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "缺少必要能力：system.administration"


def test_patch_is_retired_and_redirects_to_owning_domain():
    with pytest.raises(HTTPException) as error:
        data_browser_admin.patch_data_browser_row(
            table="orders",
            row_id_str="TEST_ROUTE_001",
            principal=_principal(),
        )

    assert error.value.status_code == 410
    assert error.value.detail["code"] == "data_browser_write_retired"
    assert "Preview/Apply" in error.value.detail["replacement"]


def test_source_correction_preview_delegates_to_typed_workflow(monkeypatch):
    class _Connection:
        def close(self):
            return None

    monkeypatch.setattr(data_browser_admin, "get_connection", lambda: _Connection())
    monkeypatch.setattr(
        data_browser_admin.source_data_correction,
        "preview",
        lambda _repository, table, row_id, updates: {
            "table": table, "row_id": row_id, "changes": updates
        },
    )

    response = data_browser_admin.preview_source_correction(
        "clients",
        1,
        DataBrowserSourceCorrectionPreviewRequest(updates={"phone": "0988"}),
        _principal(),
    )

    assert response.data == {"table": "clients", "row_id": 1, "changes": {"phone": "0988"}}

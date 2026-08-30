"""Data Browser routes must reuse the formal administrator dependency."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies import admin_auth
from api.routes import data_browser_admin
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


def test_admin_router_allows_any_authenticated_enabled_internal_role(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setattr(
        admin_auth,
        "get_admin_session",
        lambda _token, **_: _principal("line_manager"),
    )
    monkeypatch.setattr(
        data_browser_admin.data_browser_maintenance,
        "get_data_browser_table_schema",
        lambda _table, **_: {
            "rows": [],
            "columns": [],
            "primary_key": "case_no",
            "editable_columns": [],
            "valid_options": {},
            "read_only": True,
        },
    )

    response = _client().get(
        "/api/v1/admin/data-browser/orders",
        headers=_headers(),
    )

    assert response.status_code == 200


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


@pytest.mark.parametrize(
    "operation",
    (data_browser_admin.preview_source_correction, data_browser_admin.apply_source_correction),
)
def test_source_correction_is_retired(operation):
    with pytest.raises(HTTPException) as error:
        operation("clients", 1, _principal())

    assert error.value.status_code == 410
    assert error.value.detail == {
        "code": "data_browser_write_retired",
        "table": "clients",
        "row_id": 1,
        "replacement": "Use the owning Domain typed Preview/Apply command.",
    }

"""Data Browser routes must reuse the formal administrator dependency."""

import pytest
from fastapi import FastAPI
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


@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("PATCH", "/api/v1/admin/data-browser/orders/TEST_ROUTE_001"),
        ("POST", "/api/v1/admin/data-browser/clients/1/source-correction/preview"),
        ("POST", "/api/v1/admin/data-browser/clients/1/source-correction/apply"),
    ),
)
def test_retired_writers_are_no_longer_registered(method, path):
    response = _client().request(method, path, json={})

    assert response.status_code == 404

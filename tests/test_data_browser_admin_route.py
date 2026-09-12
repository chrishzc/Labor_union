"""Only the authenticated bounded archive Query remains in Data Browser."""

from unittest.mock import MagicMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import admin_auth
from api.routes import data_browser_admin
from infrastructure.mysql import mysql_adapter
from subsystems.access.authentication_session import AdminPrincipal


def _principal(role: str = "system_admin") -> AdminPrincipal:
    return AdminPrincipal(7, "verified-admin", "Verified Admin", role)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(data_browser_admin.router)
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer session-token"}


def test_admin_router_get_without_session_returns_401(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    connect = Mock(side_effect=AssertionError("unauthenticated query must not read DB"))
    monkeypatch.setattr(data_browser_admin, "get_connection", connect)

    response = _client().get("/api/v1/admin/data-browser/sources/orders")

    assert response.status_code == 401
    assert response.json()["detail"] == "缺少有效的管理員 Session"
    connect.assert_not_called()


def test_archive_query_allows_authenticated_internal_role_and_preserves_bounds(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setattr(admin_auth, "get_admin_session", lambda _token, **_: _principal("line_manager"))
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    monkeypatch.setattr(data_browser_admin, "get_connection", lambda: connection)

    response = _client().get(
        "/api/v1/admin/data-browser/sources/clients?limit=1&after=7&query=review",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"source_id": "clients", "items": [], "next_cursor": None}
    sql, params = cursor.execute.call_args.args
    assert "LIMIT %s" in sql
    assert params[-1] == 2
    assert any("review" in str(value) for value in params)
    connection.close.assert_called_once_with()


@pytest.mark.parametrize("limit", (0, 101))
def test_archive_query_rejects_invalid_limit_before_database_access(monkeypatch, limit):
    client = _client()
    client.app.dependency_overrides[admin_auth.require_system_admin] = _principal
    connect = Mock(side_effect=AssertionError("invalid limit must not read DB"))
    monkeypatch.setattr(data_browser_admin, "get_connection", connect)

    response = client.get(f"/api/v1/admin/data-browser/sources/orders?limit={limit}")

    assert response.status_code == 422
    connect.assert_not_called()


@pytest.mark.parametrize("authenticated", (False, True))
@pytest.mark.parametrize("table", (
    "actual_hours_adjustments", "beclass_records", "case_staff_assignments",
    "client_payment_transactions", "client_payments", "clients", "holidays",
    "line_confirmation_requests", "matching_records", "orders",
    "payment_migration_reviews", "staff", "staff_bank_accounts", "staff_bookings",
    "staff_payment_transactions", "staff_payments", "staff_schedule",
))
def test_raw_table_get_is_absent_and_cannot_read_database(monkeypatch, table, authenticated):
    client = _client()
    if authenticated:
        client.app.dependency_overrides[admin_auth.require_system_admin] = _principal
    connect = Mock(side_effect=AssertionError("retired path must not read DB"))
    raw_reader = Mock(side_effect=AssertionError("retired path must not call raw reader"))
    monkeypatch.setattr(data_browser_admin, "get_connection", connect)
    monkeypatch.setattr(mysql_adapter, "get_connection", connect)
    monkeypatch.setattr(mysql_adapter, "get_table_data", raw_reader)

    response = client.get(f"/api/v1/admin/data-browser/{table}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    connect.assert_not_called()
    raw_reader.assert_not_called()


def test_openapi_exposes_only_bounded_archive_query():
    schema = _client().app.openapi()
    assert set(schema["paths"]) == {"/api/v1/admin/data-browser/sources/{source_id}"}
    assert set(schema["paths"]["/api/v1/admin/data-browser/sources/{source_id}"]) == {"get"}
    assert "DataBrowserTableResponse" not in schema["components"]["schemas"]


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

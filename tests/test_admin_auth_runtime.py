"""Runtime contracts for governed administrator login and development bypass."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, Request

from api.dependencies.admin_auth import require_admin
from api.routes import admin_auth, line_admin, line_rich_menus
from api.schemas.admin_auth import AdminLoginRequest
from subsystems.access import authentication_session
from subsystems.access.authentication_session import (
    CAPABILITY_REGISTRY,
    AdminPrincipal,
    AdminSessionSchemaError,
    authenticate_admin,
)
from subsystems.line.rich_menu_publication_workflow import (
    RichMenuPublicationConflictError,
)


def test_login_reports_missing_absolute_expiry_schema(monkeypatch):
    connection = _SchemaMissingConnection()
    monkeypatch.setattr(authentication_session, "get_connection", lambda: connection)

    with pytest.raises(AdminSessionSchemaError, match="absolute_expires_at"):
        authenticate_admin("admin", "password", session_minutes=30)

    assert connection.rolled_back
    assert connection.closed


def test_login_route_returns_typed_schema_unavailable(monkeypatch):
    def fail_authentication(*_args, **_kwargs):
        raise AdminSessionSchemaError("缺少 absolute_expires_at")

    monkeypatch.setattr(admin_auth, "authenticate_admin", fail_authentication)
    request = _login_request()

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            admin_auth.login(
                AdminLoginRequest(username="admin", password="password"),
                request,
            )
        )

    assert raised.value.status_code == 503
    assert raised.value.detail["code"] == "admin_session_schema_not_ready"
    assert raised.value.detail["retryable"] is True


def test_login_route_returns_typed_invalid_credentials(monkeypatch):
    monkeypatch.setattr(admin_auth, "authenticate_admin", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(admin_auth, "record_admin_audit", lambda **_kwargs: None)
    request = _login_request()

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            admin_auth.login(
                AdminLoginRequest(username="admin", password="wrong"),
                request,
            )
        )

    assert raised.value.status_code == 401
    assert raised.value.detail["code"] == "admin_credentials_invalid"
    assert raised.value.detail["message"] == "帳號或密碼錯誤"


def test_development_bypass_cannot_publish_to_line(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    request = Request({"type": "http"})

    principal = require_admin(request, None)

    assert "line.config.manage" in principal.effective_capabilities()
    assert "line.menu.publish" not in principal.effective_capabilities()
    assert "line.rich_menu.publish" not in principal.effective_capabilities()


def test_capability_projection_ignores_legacy_persisted_subsets():
    principal = AdminPrincipal(
        7,
        "authenticated-user",
        "已驗證內部使用者",
        "system_admin",
        capabilities=frozenset({"line.config.read"}),
    )

    response = line_admin.line_admin_capabilities(principal)

    assert response.data["effective_capabilities"] == sorted(CAPABILITY_REGISTRY)


def test_rich_menu_stale_preview_returns_typed_conflict():
    error = RichMenuPublicationConflictError(
        "請重新預覽",
        code="rich_menu_preview_stale",
    )

    with pytest.raises(HTTPException) as raised:
        line_rich_menus._publication_error(error)

    assert raised.value.status_code == 409
    assert raised.value.detail == {
        "code": "rich_menu_preview_stale",
        "message": "請重新預覽",
        "retryable": False,
    }


def test_session_idle_expiry_never_exceeds_absolute_deadline():
    now = datetime.now(timezone.utc)
    absolute = now + timedelta(minutes=5)

    assert authentication_session._session_expiry(now, absolute) == absolute


class _SchemaMissingCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, _parameters=None):
        return None

    def fetchall(self):
        return [{"column_name": "expires_at"}]


class _SchemaMissingConnection:
    def __init__(self):
        self.rolled_back = False
        self.closed = False

    def begin(self):
        return None

    def cursor(self, *_args):
        return _SchemaMissingCursor()

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _login_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/admin/auth/login",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        }
    )

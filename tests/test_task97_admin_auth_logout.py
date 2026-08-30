"""
File: test_task97_admin_auth_logout.py
Description: 驗證管理員登出端點的 closed typed response 契約。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.routes import admin_auth
from api.schemas.admin_auth import AdminLogoutResponse
from subsystems.access.authentication_session import AdminPrincipal, AdminSessionStorageError


def _app_for_logout(principal: AdminPrincipal) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_auth.router)
    app.dependency_overrides[require_admin] = lambda: principal
    return app


def test_logout_returns_closed_typed_result_and_preserves_bearer_path(monkeypatch):
    principal = AdminPrincipal(7, "operator", "操作人員", "line_viewer")
    revoked_tokens: list[str] = []

    def revoke(token: str, **_kwargs) -> None:
        revoked_tokens.append(token)

    monkeypatch.setattr(admin_auth, "revoke_admin_session", revoke)

    with TestClient(_app_for_logout(principal)) as client:
        response = client.post(
            "/api/v1/admin/auth/logout",
            headers={"Authorization": "Bearer opaque-session-token"},
        )

    assert response.status_code == 200
    assert response.json()["data"] == {"logged_out": True}
    assert revoked_tokens == ["opaque-session-token"]
    assert "set-cookie" not in response.headers


def test_logout_direct_result_is_typed_and_storage_failure_remains_typed_http_error(monkeypatch):
    principal = AdminPrincipal(7, "operator", "操作人員", "line_viewer")
    monkeypatch.setattr(admin_auth, "revoke_admin_session", lambda _token, **_kwargs: None)

    result = asyncio.run(admin_auth.logout("Bearer opaque-session-token", principal))
    assert isinstance(result.data, AdminLogoutResponse)
    assert result.data.logged_out is True

    def unavailable(_token: str, **_kwargs) -> None:
        raise AdminSessionStorageError("session storage unavailable")

    monkeypatch.setattr(admin_auth, "revoke_admin_session", unavailable)
    with pytest.raises(admin_auth.HTTPException) as raised:
        asyncio.run(admin_auth.logout("Bearer opaque-session-token", principal))
    assert raised.value.status_code == 503
    assert raised.value.detail["code"] == "admin_session_storage_unavailable"

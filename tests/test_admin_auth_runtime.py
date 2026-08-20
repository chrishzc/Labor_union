"""
File: test_admin_auth_runtime.py
Description: 驗證管理後台 TOTP 登入、Session 與開發 bypass 的 runtime 契約。
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    AdminLoginRateLimitedError,
    PasswordLoginChallenge,
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
                AdminLoginRequest(username="admin", password="password", totp_code="123456"),
                request,
            )
        )

    assert raised.value.status_code == 503
    assert raised.value.detail["code"] == "admin_session_schema_not_ready"
    assert raised.value.detail["retryable"] is True


def test_login_route_returns_typed_invalid_credentials(monkeypatch):
    monkeypatch.setattr(admin_auth, "authenticate_admin", lambda *_args, **_kwargs: None)
    request = _login_request()

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            admin_auth.login(
                AdminLoginRequest(username="admin", password="wrong", totp_code="123456"),
                request,
            )
        )

    assert raised.value.status_code == 401
    assert raised.value.detail["code"] == "invalid_credentials_or_factor"
    assert raised.value.detail["message"] == "帳號、密碼或驗證碼錯誤"


def test_first_login_can_omit_totp_until_mfa_enrollment_is_issued():
    request = AdminLoginRequest(username="admin", password="password")

    assert request.totp_code is None


def test_password_challenge_route_never_issues_a_session_before_factor_verification(monkeypatch):
    challenge = PasswordLoginChallenge("challenge-1", "x" * 48, datetime(2026, 8, 16, 12, 5, 0))
    monkeypatch.setattr(admin_auth, "issue_password_login_challenge", lambda *_args, **_kwargs: challenge)

    response = asyncio.run(
        admin_auth.issue_login_challenge(
            admin_auth.AdminPasswordChallengeRequest(username="admin", password="password"), _login_request()
        )
    )

    assert response.data.challenge_id == "challenge-1"
    assert not hasattr(response.data, "access_token")
    assert response.data.expires_at.tzinfo is not None
    assert response.data.expires_at.utcoffset() == timedelta(0)


def test_factor_verification_route_issues_session_only_after_valid_challenge(monkeypatch):
    principal = AdminPrincipal(1, "admin", "管理員", "system_admin", is_root=True)
    monkeypatch.setattr(
        admin_auth,
        "complete_password_login_challenge",
        lambda **_kwargs: ("session-token", datetime(2026, 8, 16, 12, 30, 0), principal),
    )

    response = asyncio.run(
        admin_auth.verify_login_challenge(
            "challenge-1",
            admin_auth.AdminFactorVerificationRequest(challenge_token="x" * 48, factor_code="123456"),
            _login_request(),
        )
    )

    assert response.data.access_token == "session-token"
    assert response.data.expires_at.tzinfo is not None
    assert response.data.expires_at.utcoffset() == timedelta(0)


def test_refresh_route_normalizes_repository_utc_naive_expiry(monkeypatch):
    principal = AdminPrincipal(1, "admin", "管理員", "system_admin", is_root=True)
    monkeypatch.setattr(
        admin_auth,
        "renew_admin_session",
        lambda *_args, **_kwargs: datetime(2026, 8, 16, 12, 30, 0),
    )

    response = asyncio.run(admin_auth.refresh("Bearer session-token", principal))

    assert response.data.expires_at.tzinfo is not None
    assert response.data.expires_at.utcoffset() == timedelta(0)


def test_password_challenge_route_returns_typed_rate_limit(monkeypatch):
    def rate_limited(*_args, **_kwargs):
        raise AdminLoginRateLimitedError()

    monkeypatch.setattr(admin_auth, "issue_password_login_challenge", rate_limited)

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            admin_auth.issue_login_challenge(
                admin_auth.AdminPasswordChallengeRequest(username="admin", password="password"),
                _login_request(),
            )
        )

    assert raised.value.status_code == 429
    assert raised.value.detail["code"] == "login_rate_limited"


def test_login_attempt_window_uses_injected_clock_boundary():
    cursor = _AttemptCursor(attempt_count=5)
    now = datetime(2026, 8, 16, 12, 0, 0)

    assert authentication_session._is_rate_limited(cursor, "admin", "127.0.0.1", now=now)
    assert cursor.parameters[-1] == now - timedelta(minutes=15)

    authentication_session._record_login_attempt(cursor, "admin", "127.0.0.1", "failed", now=now)
    assert cursor.parameters[-1] == now


def test_development_bypass_cannot_publish_to_line(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "local_bypass")
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


def test_login_enrollment_and_session_queries_load_the_account_version():
    source = Path(authentication_session.__file__).read_text(encoding="utf-8")

    assert source.count("u.access_control_version") >= 2
    assert "enabled, access_control_version, " in source


class _SchemaMissingCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, _parameters=None):
        return None

    def fetchall(self):
        return [{"column_name": "expires_at"}]


class _AttemptCursor:
    def __init__(self, attempt_count: int):
        self.attempt_count = attempt_count
        self.parameters = ()

    def execute(self, _query, parameters):
        self.parameters = parameters

    def fetchone(self):
        return {"attempt_count": self.attempt_count}


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

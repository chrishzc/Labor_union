"""
File: test_access_control_ui_app_test.py
Description: 驗證 Streamlit 全域 guard、QR 綁定與一次性登入 challenge 行為。
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


def _access_control_shell_test_app() -> None:
    """供 AppTest 執行的最小 shell，避免載入實際業務頁的外部依賴。"""
    import builtins
    import importlib
    import os
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(os.getcwd()).resolve()))
    app = importlib.import_module("ui.app")
    client_module = importlib.import_module("ui.api_clients.access_control_api_client")
    view = client_module.AdminPrincipalView

    class _Client:
        def me(self, token):
            builtins._ACCESS_CONTROL_UI_CALLS.append(("me", token))
            if token == "expired-token":
                raise client_module.AccessControlApiError(
                    "expired", status_code=401, code="invalid_session"
                )
            return view(
                id=1, username="root", display_name="Root", role="system_admin",
                capabilities=[], is_root=True,
            )

        def logout(self, token):
            builtins._ACCESS_CONTROL_UI_CALLS.append(("logout", token))

        def development_session(self):
            raise RuntimeError("not used")

        def issue_password_challenge(self, **_kwargs):
            raise RuntimeError("not used")

    app.AccessControlApiClient = _Client
    app.DEFAULT_PAGE_TITLE = "Test page"
    app.PAGE_REGISTRY = {"Test": (("Test page", "unused"),)}
    app._load_page_show = lambda _name: lambda: None
    app.main()


def _run_shell(*, token: str | None) -> AppTest:
    app = AppTest.from_function(_access_control_shell_test_app)
    if token is not None:
        app.session_state["line_admin_access_token"] = token
    app.run(timeout=10)
    return app


def _factor_failure_test_app() -> None:
    """以最小 client 驗證第二段失敗時，不會保留可重送的 challenge。"""
    import importlib

    app = importlib.import_module("ui.app")
    client_module = importlib.import_module("ui.api_clients.access_control_api_client")

    class _Client:
        def verify_password_challenge(self, **_kwargs):
            raise client_module.AccessControlApiError(
                "驗證失敗", status_code=401, code="invalid_credentials_or_factor"
            )

    app._render_login_or_enrollment(_Client())


def _enrollment_success_test_app() -> None:
    """驗證 Stage 1 typed success 會切到既有 QR enrollment 畫面。"""
    import importlib

    app = importlib.import_module("ui.app")
    client_module = importlib.import_module("ui.api_clients.access_control_api_client")

    class _Client:
        def issue_password_challenge(self, **_kwargs):
            return client_module.PasswordChallengeView(
                challenge_type="mfa_enrollment",
                challenge_id="enrollment-id",
                challenge_token="x" * 48,
                expires_at="2026-08-20T12:30:00Z",
                provisioning_uri=(
                    "otpauth://totp/Labor%20Union%20Admin:root"
                    "?secret=JBSWY3DPEHPK3PXP&issuer=Labor%20Union%20Admin"
                ),
            )

    app._render_login_or_enrollment(_Client())


def test_empty_rollback_query_params_are_valid(monkeypatch) -> None:
    from ui import app

    monkeypatch.setattr(app.st, "query_params", {})

    assert app._consume_rollback_query() is True


def test_nonempty_invalid_rollback_query_params_fail_closed(monkeypatch) -> None:
    from ui import app

    params = {"entry": "unknown"}
    monkeypatch.setattr(app.st, "query_params", params)

    assert app._consume_rollback_query() is False
    assert params == {}


def test_global_guard_renders_login_before_navigation(monkeypatch):
    import builtins

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setattr(builtins, "_ACCESS_CONTROL_UI_CALLS", [], raising=False)

    app = _run_shell(token=None)

    assert not app.exception
    assert any(title.value == "管理後台登入" for title in app.title)
    assert not app.sidebar.radio
    assert builtins._ACCESS_CONTROL_UI_CALLS == []


def test_global_guard_allows_verified_session_and_logout(monkeypatch):
    import builtins

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setattr(builtins, "_ACCESS_CONTROL_UI_CALLS", [], raising=False)

    app = _run_shell(token="active-token")

    assert not app.exception
    assert app.sidebar.radio
    assert ("me", "active-token") in builtins._ACCESS_CONTROL_UI_CALLS
    app.sidebar.button(key="global_admin_logout").click().run(timeout=10)
    assert ("logout", "active-token") in builtins._ACCESS_CONTROL_UI_CALLS
    assert "line_admin_access_token" not in app.session_state


def test_global_guard_removes_expired_token_before_rendering_navigation(monkeypatch):
    import builtins

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setattr(builtins, "_ACCESS_CONTROL_UI_CALLS", [], raising=False)

    app = _run_shell(token="expired-token")

    assert not app.exception
    assert not app.sidebar.radio
    assert "line_admin_access_token" not in app.session_state


def test_enrollment_qr_is_memory_png_and_rejects_non_totp_uri() -> None:
    from ui.app import _enrollment_qr_png

    image = _enrollment_qr_png(
        "otpauth://totp/Labor%20Union%20Admin:root?secret=JBSWY3DPEHPK3PXP&issuer=Labor%20Union%20Admin"
    )

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError, match="provisioning URI"):
        _enrollment_qr_png("https://untrusted.example/qr")


def test_factor_failure_discards_single_use_challenge() -> None:
    app = AppTest.from_function(_factor_failure_test_app)
    app.session_state["access_control_password_challenge"] = {
        "id": "challenge-id",
        "token": "challenge-token",
    }
    app.run(timeout=10)

    app.text_input[0].input("123456")
    app.button[0].click().run(timeout=10)

    assert not app.exception
    assert "access_control_password_challenge" not in app.session_state
    assert any("已作廢" in info.value for info in app.info)


def test_enrollment_success_response_renders_qr_flow() -> None:
    app = AppTest.from_function(_enrollment_success_test_app)
    app.run(timeout=10)

    app.text_input[0].input("root")
    app.text_input[1].input("password")
    app.button[0].click().run(timeout=10)

    assert not app.exception
    enrollment = app.session_state["access_control_enrollment"]
    assert enrollment["id"] == "enrollment-id"
    assert enrollment["provisioning_uri"].startswith("otpauth://totp/")
    assert any("掃描 QR code" in info.value for info in app.info)


def test_access_control_client_decodes_global_typed_error(monkeypatch) -> None:
    from ui.api_clients.access_control_api_client import (
        AccessControlApiClient,
        AccessControlApiError,
    )

    class _Response:
        ok = False
        status_code = 401

        @staticmethod
        def json():
            return {
                "detail": {
                    "error": {
                        "category": "forbidden",
                        "code": "invalid_credentials_or_factor",
                        "message": "帳號、密碼或驗證碼錯誤",
                        "field_errors": [],
                        "domain_blockers": [],
                        "retryable": False,
                        "correlation_id": "test-correlation",
                        "current_version": None,
                    }
                }
            }

    monkeypatch.setattr(
        "ui.api_clients.access_control_api_client.requests.request",
        lambda *_args, **_kwargs: _Response(),
    )

    with pytest.raises(AccessControlApiError) as raised:
        AccessControlApiClient().issue_password_challenge(
            username="root", password="wrong"
        )

    assert raised.value.code == "invalid_credentials_or_factor"
    assert str(raised.value) == "帳號、密碼或驗證碼錯誤"

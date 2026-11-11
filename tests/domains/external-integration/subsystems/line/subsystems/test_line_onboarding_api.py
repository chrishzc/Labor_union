"""
File: test_line_onboarding_api.py
Description: 驗證加入好友歡迎訊息退役後 /api/v1/line/onboarding 端點固定回傳 410 GONE。
"""

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None
    TestClient = None

if HAS_FASTAPI:
    from api.dependencies.admin_auth import (
        require_line_configuration_manager,
        require_line_configuration_reader,
    )
from domains.line.identity_flow import LineIdentityFlowPurpose
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.webhook_identity_handlers import _identity_link_message


def _principal() -> AdminPrincipal:
    return AdminPrincipal(1, "admin", "管理員", "system_admin")


def _client() -> TestClient:
    if not HAS_FASTAPI:
        pytest.skip("fastapi is not installed in this environment")
    from api.routes import line_onboarding
    app = FastAPI()
    app.include_router(line_onboarding.router)
    app.dependency_overrides[require_line_configuration_reader] = _principal
    app.dependency_overrides[require_line_configuration_manager] = _principal
    return TestClient(app)


def test_onboarding_endpoints_are_retired_with_410_gone() -> None:
    if not HAS_FASTAPI:
        pytest.skip("fastapi is not installed in this environment")
    client = _client()
    for method, path, kwargs in (
        ("get", "/api/v1/line/onboarding", {}),
        ("post", "/api/v1/line/onboarding/preview", {"json": {"content": "測試：{url}"}}),
        ("put", "/api/v1/line/onboarding", {"json": {"content": "測試：{url}", "expected_revision": 1}}),
    ):
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 410
        assert response.json()["detail"]["code"] == "line_onboarding_welcome_retired"


def test_customer_binding_link_message_does_not_use_welcome_prose() -> None:
    msg = _identity_link_message(LineIdentityFlowPurpose.CUSTOMER_BINDING, "https://liff.test/abc", unit_of_work=None)
    assert "https://liff.test/abc" in msg
    assert "請開啟以下頁面完成客戶身分綁定或服務登記" in msg
    assert "歡迎加入" not in msg


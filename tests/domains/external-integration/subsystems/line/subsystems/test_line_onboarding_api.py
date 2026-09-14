"""
File: test_line_onboarding_api.py
Description: 驗證 LINE 新好友 Onboarding 歡迎訊息的查詢、預覽與手動編輯更新 API。
"""

import json
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None
    TestClient = None

import pytest

if HAS_FASTAPI:
    from api.dependencies.admin_auth import (
        require_line_configuration_manager,
        require_line_configuration_reader,
    )
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationRevisionConflict,
    LineConfigurationSnapshot,
)
from domains.line.identities import LineConfigurationRevision
from domains.line.identity_flow import LineIdentityFlowPurpose
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationResult,
    LineConfigurationCommandOutcome,
)
from subsystems.line.webhook_identity_handlers import (
    DEFAULT_ONBOARDING_WELCOME_MESSAGE,
    _identity_link_message,
)


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


def test_default_onboarding_message_has_no_stale_ai_text() -> None:
    assert "AI 小幫手" not in DEFAULT_ONBOARDING_WELCOME_MESSAGE
    assert "24 小時為您即時解答" not in DEFAULT_ONBOARDING_WELCOME_MESSAGE
    assert "服務說明" in DEFAULT_ONBOARDING_WELCOME_MESSAGE
    assert "轉真人客服" in DEFAULT_ONBOARDING_WELCOME_MESSAGE
    assert "{url}" in DEFAULT_ONBOARDING_WELCOME_MESSAGE


def test_get_onboarding_returns_configured_message(monkeypatch) -> None:
    if not HAS_FASTAPI:
        pytest.skip("fastapi is not installed in this environment")
    from api.routes import line_onboarding
    test_content = "工會歡迎您！請至專屬頁面：{url} 完成登記。"

    class MockApp:
        def get(self, kind, actor):
            assert kind is LineConfigurationKind.MESSAGE_TEMPLATES
            definition = {
                "version": 1,
                "templates": [
                    {
                        "id": "customer_onboarding_welcome",
                        "content": test_content,
                        "enabled": True,
                    }
                ],
            }
            return LineConfigurationSnapshot(
                kind,
                LineConfigurationRevision(3),
                canonical_line_payload_json(definition),
            )

    monkeypatch.setattr(
        line_onboarding,
        "get_line_configuration_application",
        lambda: MockApp(),
    )
    client = _client()
    response = client.get("/api/v1/line/onboarding")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["template_id"] == "customer_onboarding_welcome"
    assert data["content"] == test_content
    assert data["revision"] == 3
    assert "{url}" not in data["sample_preview"]
    assert "https://liff.line.me" in data["sample_preview"]
    assert data["variables"] == ["url"]


def test_preview_onboarding_message() -> None:
    if not HAS_FASTAPI:
        pytest.skip("fastapi is not installed in this environment")
    client = _client()
    draft = "自訂歡迎詞：{url}。有問題請隨時回覆。"
    response = client.post("/api/v1/line/onboarding/preview", json={"content": draft})
    assert response.status_code == 200
    data = response.json()["data"]
    assert "{url}" not in data["sample_preview"]
    assert "https://liff.line.me" in data["sample_preview"]
    assert data["variables"] == ["url"]


def test_update_onboarding_message_applies_new_revision(monkeypatch) -> None:
    if not HAS_FASTAPI:
        pytest.skip("fastapi is not installed in this environment")
    from api.routes import line_onboarding
    new_content = "最新歡迎詞：請開啟 {url} 登記！"
    applied_calls = []

    class MockApp:
        def get(self, kind, actor):
            return LineConfigurationSnapshot(
                kind,
                LineConfigurationRevision(2),
                canonical_line_payload_json({"version": 1, "templates": []}),
            )

        def apply(self, *, kind, expected_revision, definition, actor, reason, idempotency_key, correlation_id):
            assert kind is LineConfigurationKind.MESSAGE_TEMPLATES
            assert expected_revision == LineConfigurationRevision(2)
            applied_calls.append((definition, reason))
            return ApplyLineConfigurationResult(
                outcome=LineConfigurationCommandOutcome.CREATED,
                snapshot=LineConfigurationSnapshot(
                    kind,
                    LineConfigurationRevision(3),
                    canonical_line_payload_json(definition),
                ),
            )

    monkeypatch.setattr(
        line_onboarding,
        "get_line_configuration_application",
        lambda: MockApp(),
    )
    client = _client()
    response = client.put(
        "/api/v1/line/onboarding",
        json={
            "content": new_content,
            "expected_revision": 2,
            "reason": "手動修改歡迎訊息",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] == new_content
    assert data["revision"] == 3
    assert len(applied_calls) == 1
    saved_def, saved_reason = applied_calls[0]
    assert saved_reason == "手動修改歡迎訊息"
    target_tpl = next(t for t in saved_def["templates"] if t["id"] == "customer_onboarding_welcome")
    assert target_tpl["content"] == new_content


def test_update_onboarding_message_revision_conflict(monkeypatch) -> None:
    if not HAS_FASTAPI:
        pytest.skip("fastapi is not installed in this environment")
    from api.routes import line_onboarding

    class MockApp:
        def get(self, kind, actor):
            return LineConfigurationSnapshot(
                kind,
                LineConfigurationRevision(5),
                canonical_line_payload_json({"version": 1, "templates": []}),
            )

        def apply(self, **kwargs):
            raise LineConfigurationRevisionConflict("revision mismatch")

    monkeypatch.setattr(
        line_onboarding,
        "get_line_configuration_application",
        lambda: MockApp(),
    )
    client = _client()
    response = client.put(
        "/api/v1/line/onboarding",
        json={
            "content": "衝突測試：{url}",
            "expected_revision": 4,
            "reason": "測試衝突",
        },
    )
    assert response.status_code == 409


def test_identity_link_message_renders_custom_template() -> None:
    from domains.line.canonical_payload import canonical_line_payload_json

    class MockConfigurations:
        def get(self, kind):
            assert kind is LineConfigurationKind.MESSAGE_TEMPLATES
            definition = {
                "version": 1,
                "templates": [
                    {
                        "id": "customer_onboarding_welcome",
                        "name": "自訂歡迎詞",
                        "category": "webhook_reply",
                        "message_type": "text",
                        "enabled": True,
                        "content": "自訂工會歡迎詞！請前往 {url}",
                        "variables": [{"name": "url", "required": True}],
                    }
                ],
            }
            return LineConfigurationSnapshot(kind, LineConfigurationRevision(1), canonical_line_payload_json(definition))

    class MockUoW:
        configurations = MockConfigurations()

    msg = _identity_link_message(LineIdentityFlowPurpose.CUSTOMER_BINDING, "https://liff.test/123", unit_of_work=MockUoW())
    assert msg == "自訂工會歡迎詞！請前往 https://liff.test/123"


def test_identity_link_message_falls_back_to_modern_default_when_no_config() -> None:
    msg = _identity_link_message(LineIdentityFlowPurpose.CUSTOMER_BINDING, "https://liff.test/abc", unit_of_work=None)
    assert "https://liff.test/abc" in msg
    assert "AI 小幫手" not in msg
    assert "服務說明" in msg


from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.routes import llm_configuration
from infrastructure.runtime.llm_api_key_store import LlmApiKeyStore


class _Selector:
    def __init__(self, result: str = "OK", error: Exception | None = None) -> None:
        self.model = "gemini-3.5-flash-lite"
        self._result = result
        self._error = error
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self._error is not None:
            raise self._error
        return self._result


def _client(tmp_path, selector: _Selector | None = None):
    store = LlmApiKeyStore(tmp_path / "llm_api_key")
    active_selector = selector or _Selector()
    app = FastAPI()
    app.include_router(llm_configuration.router)
    app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(
        username="system-admin"
    )
    app.dependency_overrides[llm_configuration.get_llm_api_key_store] = lambda: store
    app.dependency_overrides[llm_configuration.get_gemini_selector] = lambda: active_selector
    return TestClient(app), store, active_selector


def test_llm_api_key_is_write_only_over_http(tmp_path) -> None:
    client, store, _ = _client(tmp_path)
    secret = "sk-test-write-only-123456789"

    response = client.post("/api/v1/system/llm/api-key", json={"api_key": secret})

    assert response.status_code == 200
    assert secret not in response.text
    assert response.json()["data"]["configured"] is True
    assert set(response.json()["data"]) == {"configured", "updated_at"}
    assert store.read_for_runtime() == secret

    status_response = client.get("/api/v1/system/llm/api-key/status")
    assert status_response.status_code == 200
    assert secret not in status_response.text
    assert set(status_response.json()["data"]) == {"configured", "updated_at"}


def test_invalid_llm_api_key_is_not_echoed_in_validation_response(tmp_path) -> None:
    client, _, _ = _client(tmp_path)
    invalid_secret = "short"

    response = client.post(
        "/api/v1/system/llm/api-key",
        json={"api_key": invalid_secret},
    )

    assert response.status_code == 422
    assert invalid_secret not in response.text


def test_replacing_llm_api_key_does_not_expose_previous_value(tmp_path) -> None:
    client, store, _ = _client(tmp_path)
    first_secret = "sk-test-first-123456789"
    second_secret = "sk-test-second-987654321"

    assert client.post(
        "/api/v1/system/llm/api-key", json={"api_key": first_secret}
    ).status_code == 200
    response = client.post(
        "/api/v1/system/llm/api-key", json={"api_key": second_secret}
    )

    assert response.status_code == 200
    assert first_secret not in response.text
    assert second_secret not in response.text
    assert store.read_for_runtime() == second_secret


def test_connection_test_returns_only_safe_status(tmp_path) -> None:
    selector = _Selector(result="OK")
    client, store, _ = _client(tmp_path, selector)
    secret = "google-ai-studio-secret-value"
    store.replace(secret)

    response = client.post("/api/v1/system/llm/connection-test")

    assert response.status_code == 200
    assert secret not in response.text
    assert response.json()["data"] == {
        "connected": True,
        "provider": "google_ai_studio",
        "model": "gemini-3.5-flash-lite",
        "code": None,
    }
    assert selector.prompts == ["連線測試。只回覆 OK。"]


def test_connection_test_maps_provider_failure_without_secret(tmp_path) -> None:
    selector = _Selector(error=RuntimeError("gemini_api_http_403"))
    client, store, _ = _client(tmp_path, selector)
    secret = "google-ai-studio-secret-value"
    store.replace(secret)

    response = client.post("/api/v1/system/llm/connection-test")

    assert response.status_code == 200
    assert secret not in response.text
    assert response.json()["data"] == {
        "connected": False,
        "provider": "google_ai_studio",
        "model": "gemini-3.5-flash-lite",
        "code": "authentication_failed",
    }

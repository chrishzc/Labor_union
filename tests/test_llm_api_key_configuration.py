from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.routes import llm_configuration
from infrastructure.runtime.llm_api_key_store import LlmApiKeyStore


def _client(tmp_path):
    store = LlmApiKeyStore(tmp_path / "llm_api_key")
    app = FastAPI()
    app.include_router(llm_configuration.router)
    app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(
        username="system-admin"
    )
    app.dependency_overrides[llm_configuration.get_llm_api_key_store] = lambda: store
    return TestClient(app), store


def test_llm_api_key_is_write_only_over_http(tmp_path) -> None:
    client, store = _client(tmp_path)
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
    client, _ = _client(tmp_path)
    invalid_secret = "short"

    response = client.post(
        "/api/v1/system/llm/api-key",
        json={"api_key": invalid_secret},
    )

    assert response.status_code == 422
    assert invalid_secret not in response.text


def test_replacing_llm_api_key_does_not_expose_previous_value(tmp_path) -> None:
    client, store = _client(tmp_path)
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

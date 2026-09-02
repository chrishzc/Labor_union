from __future__ import annotations

import pytest
import requests

from infrastructure.knowledge.gemini_selector import (
    DEFAULT_GEMINI_MODEL,
    GeminiCandidateSelector,
)


class _Store:
    def __init__(self, value: str | None) -> None:
        self.value = value

    def read_for_runtime(self) -> str | None:
        return self.value


class _Response:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_default_model_is_cost_efficient_flash_lite() -> None:
    assert DEFAULT_GEMINI_MODEL == "gemini-3.5-flash-lite"


def test_selector_uses_server_secret_and_bounded_google_request() -> None:
    calls: list[dict] = []
    secret = "google-ai-studio-secret-value"

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _Response(
            200,
            {
                "candidates": [
                    {"content": {"parts": [{"text": "QA-013"}]}}
                ]
            },
        )

    selector = GeminiCandidateSelector(
        store=_Store(secret),
        model="gemini-3.5-flash-lite",
        post=post,
    )

    assert selector("只能選候選 ID") == "QA-013"
    assert len(calls) == 1
    call = calls[0]
    assert call["url"].endswith("/models/gemini-3.5-flash-lite:generateContent")
    assert call["headers"]["x-goog-api-key"] == secret
    assert call["json"]["contents"][0]["parts"][0]["text"] == "只能選候選 ID"
    assert call["json"]["generationConfig"]["temperature"] == 0
    assert call["json"]["generationConfig"]["maxOutputTokens"] == 64
    assert call["json"]["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "minimal"
    }
    assert secret not in str(call["json"])


def test_selector_fails_closed_when_key_is_missing() -> None:
    selector = GeminiCandidateSelector(store=_Store(None), post=lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="gemini_api_key_not_configured"):
        selector("prompt")


def test_selector_does_not_echo_secret_in_provider_errors() -> None:
    secret = "google-ai-studio-secret-value"

    def post(*_args, **_kwargs):
        raise requests.ConnectionError("network down")

    selector = GeminiCandidateSelector(store=_Store(secret), post=post)

    with pytest.raises(ConnectionError) as error:
        selector("prompt")
    assert secret not in str(error.value)


def test_selector_marks_retryable_google_status_as_connection_error() -> None:
    selector = GeminiCandidateSelector(
        store=_Store("google-ai-studio-secret-value"),
        post=lambda *_args, **_kwargs: _Response(429, {}),
    )

    with pytest.raises(ConnectionError, match="gemini_api_http_429"):
        selector("prompt")

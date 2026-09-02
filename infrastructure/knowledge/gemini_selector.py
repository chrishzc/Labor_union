"""Server-side Gemini API adapter used only to select reviewed QA candidates.

The API key is read from the private runtime secret store and is never returned
through HTTP, embedded in prompts, logged, or exposed to the React bundle.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import requests

from infrastructure.runtime.llm_api_key_store import LlmApiKeyStore


DEFAULT_GEMINI_MODEL = "gemini-3.7-flash"
_GEMINI_GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiCandidateSelector:
    """Call Gemini with a bounded prompt and return only the model text output."""

    def __init__(
        self,
        *,
        store: LlmApiKeyStore | None = None,
        model: str | None = None,
        timeout_seconds: float = 15.0,
        post: Callable[..., Any] | None = None,
    ) -> None:
        self._store = store or LlmApiKeyStore()
        self._model = (model or os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()
        self._timeout_seconds = timeout_seconds
        self._post = post or requests.post

    @property
    def model(self) -> str:
        return self._model

    def __call__(self, prompt: str) -> str:
        api_key = self._store.read_for_runtime()
        if not api_key:
            raise RuntimeError("gemini_api_key_not_configured")

        try:
            response = self._post(
                _GEMINI_GENERATE_CONTENT_URL.format(model=self._model),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0,
                        "maxOutputTokens": 64,
                        "thinkingConfig": {"thinkingLevel": "low"},
                    },
                },
                timeout=self._timeout_seconds,
            )
        except requests.Timeout as error:
            raise TimeoutError("gemini_api_timeout") from error
        except requests.RequestException as error:
            raise ConnectionError("gemini_api_unavailable") from error

        status_code = int(getattr(response, "status_code", 0))
        if status_code in {408, 429, 500, 502, 503, 504}:
            raise ConnectionError(f"gemini_api_http_{status_code}")
        if status_code < 200 or status_code >= 300:
            raise RuntimeError(f"gemini_api_http_{status_code}")

        try:
            payload = response.json()
            candidates = payload["candidates"]
            parts = candidates[0]["content"]["parts"]
            text = next(
                str(part["text"])
                for part in parts
                if isinstance(part, dict) and str(part.get("text", "")).strip()
            )
        except (KeyError, IndexError, StopIteration, TypeError, ValueError) as error:
            raise RuntimeError("gemini_api_invalid_response") from error

        return text.strip()


__all__ = ["DEFAULT_GEMINI_MODEL", "GeminiCandidateSelector"]

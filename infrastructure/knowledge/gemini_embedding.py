"""Gemini embedding adapter for multilingual knowledge retrieval."""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Sequence
from typing import Any

import requests

from infrastructure.runtime.llm_api_key_store import LlmApiKeyStore


DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_GEMINI_EMBEDDING_DIMENSION = 768
_GEMINI_BATCH_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:batchEmbedContents"
)
_MAX_BATCH_SIZE = 100


class GeminiKnowledgeEmbedder:
    """Create one compatible vector space for QA documents and user questions."""

    def __init__(
        self,
        *,
        store: LlmApiKeyStore | None = None,
        model: str | None = None,
        dimension: int | None = None,
        timeout_seconds: float = 30.0,
        post: Callable[..., Any] | None = None,
    ) -> None:
        self._store = store or LlmApiKeyStore()
        self._model = (
            model
            or os.getenv("GEMINI_EMBEDDING_MODEL")
            or DEFAULT_GEMINI_EMBEDDING_MODEL
        ).strip()
        configured_dimension = dimension or int(
            os.getenv(
                "GEMINI_EMBEDDING_DIMENSION",
                str(DEFAULT_GEMINI_EMBEDDING_DIMENSION),
            )
        )
        if configured_dimension < 128 or configured_dimension > 3072:
            raise ValueError("invalid_gemini_embedding_dimension")
        self._dimension = configured_dimension
        self._timeout_seconds = timeout_seconds
        self._post = post or requests.post

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def space_id(self) -> str:
        return f"gemini:{self._model}:{self._dimension}:qa-v1"

    def embed_documents(self, documents: Sequence[str]) -> list[list[float]]:
        prepared = [f"title: none | text: {document}" for document in documents]
        return self._embed(prepared)

    def embed_queries(self, queries: Sequence[str]) -> list[list[float]]:
        prepared = [f"task: question answering | query: {query}" for query in queries]
        return self._embed(prepared)

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        api_key = self._store.read_for_runtime()
        if not api_key:
            raise RuntimeError("gemini_api_key_not_configured")

        vectors: list[list[float]] = []
        for offset in range(0, len(texts), _MAX_BATCH_SIZE):
            vectors.extend(self._embed_batch(texts[offset : offset + _MAX_BATCH_SIZE], api_key))
        return vectors

    def _embed_batch(self, texts: Sequence[str], api_key: str) -> list[list[float]]:
        model_resource = f"models/{self._model}"
        response = None
        for attempt in range(2):
            try:
                response = self._post(
                    _GEMINI_BATCH_EMBED_URL.format(model=self._model),
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": api_key,
                    },
                    json={
                        "requests": [
                            {
                                "model": model_resource,
                                "content": {"parts": [{"text": text}]},
                                "outputDimensionality": self._dimension,
                            }
                            for text in texts
                        ]
                    },
                    timeout=self._timeout_seconds,
                )
                break
            except requests.Timeout as error:
                if attempt == 1:
                    raise TimeoutError("gemini_embedding_api_timeout") from error
            except requests.RequestException as error:
                if attempt == 1:
                    raise ConnectionError("gemini_embedding_api_unavailable") from error

        status_code = int(getattr(response, "status_code", 0))
        if status_code in {408, 429, 500, 502, 503, 504}:
            raise ConnectionError(f"gemini_embedding_api_http_{status_code}")
        if status_code < 200 or status_code >= 300:
            raise RuntimeError(f"gemini_embedding_api_http_{status_code}")

        try:
            raw_embeddings = response.json()["embeddings"]
            vectors = [
                [float(value) for value in embedding["values"]]
                for embedding in raw_embeddings
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("gemini_embedding_api_invalid_response") from error
        if len(vectors) != len(texts) or any(
            len(vector) != self._dimension
            or not all(math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise RuntimeError("gemini_embedding_api_invalid_response")
        return vectors


__all__ = [
    "DEFAULT_GEMINI_EMBEDDING_DIMENSION",
    "DEFAULT_GEMINI_EMBEDDING_MODEL",
    "GeminiKnowledgeEmbedder",
]

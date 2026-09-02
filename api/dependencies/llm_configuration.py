"""Composition root for write-only Gemini configuration and real M2 tests.

API routes depend on this application-facing service instead of importing
provider, Chroma, secret-store, or MySQL infrastructure directly.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswer,
    KnowledgeAnswerUnsupported,
)
from infrastructure.knowledge.chroma_gateway import ChromaKnowledgeGateway
from infrastructure.knowledge.gemini_selector import GeminiCandidateSelector
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)
from infrastructure.runtime.llm_api_key_store import LlmApiKeyStore


_PROVIDER = "google_ai_studio"
_CATALOG_MARKER = "AI客服QA題庫.jsonl#"


class CandidateSelectorPort(Protocol):
    @property
    def model(self) -> str: ...

    def __call__(self, prompt: str) -> str: ...


class KnowledgeAnswerGatewayPort(Protocol):
    def answer(self, question: str, index_version: int) -> KnowledgeAnswer: ...


@dataclass(frozen=True, slots=True)
class LlmSecretStatus:
    configured: bool
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class LlmConnectionTestResult:
    connected: bool
    provider: str
    model: str
    code: str | None


@dataclass(frozen=True, slots=True)
class LlmSemanticTestResult:
    outcome: str
    provider: str
    model: str
    index_version: int | None
    qa_id: str | None
    source_identity: str | None
    answer_text: str | None
    code: str | None


class LlmConfigurationApplication:
    """Own Gemini config/status plus read-only connection and M2 semantic tests."""

    def __init__(
        self,
        *,
        store: LlmApiKeyStore,
        selector: CandidateSelectorPort,
        ready_index_version: Callable[[], int | None],
        gateway_factory: Callable[[CandidateSelectorPort], KnowledgeAnswerGatewayPort],
    ) -> None:
        self._store = store
        self._selector = selector
        self._ready_index_version = ready_index_version
        self._gateway_factory = gateway_factory

    def status(self) -> LlmSecretStatus:
        value = self._store.status()
        return LlmSecretStatus(value.configured, value.updated_at)

    def replace_api_key(self, api_key: str) -> LlmSecretStatus:
        value = self._store.replace(api_key)
        return LlmSecretStatus(value.configured, value.updated_at)

    def test_connection(self) -> LlmConnectionTestResult:
        try:
            output = self._selector("連線測試。只回覆 OK。")
            connected = bool(output.strip())
            return LlmConnectionTestResult(
                connected=connected,
                provider=_PROVIDER,
                model=self._selector.model,
                code=None if connected else "empty_response",
            )
        except TimeoutError:
            code = "timeout"
        except ConnectionError as error:
            code = "rate_limited" if str(error) == "gemini_api_http_429" else "unavailable"
        except RuntimeError as error:
            code = _safe_provider_code(error)
        return LlmConnectionTestResult(
            connected=False,
            provider=_PROVIDER,
            model=self._selector.model,
            code=code,
        )

    def test_semantics(self, question: str) -> LlmSemanticTestResult:
        index_version = self._ready_index_version()
        if index_version is None:
            return self._empty_semantic_result(
                outcome="index_unavailable",
                index_version=None,
                code="knowledge_index_unavailable",
            )

        try:
            answer = self._gateway_factory(self._selector).answer(
                question,
                int(index_version),
            )
        except KnowledgeAnswerUnsupported:
            return self._empty_semantic_result(
                outcome="unsupported",
                index_version=int(index_version),
                code="knowledge_answer_unsupported",
            )
        except TimeoutError:
            return self._empty_semantic_result(
                outcome="provider_error",
                index_version=int(index_version),
                code="timeout",
            )
        except ConnectionError as error:
            code = "rate_limited" if str(error) == "gemini_api_http_429" else "unavailable"
            return self._empty_semantic_result(
                outcome="provider_error",
                index_version=int(index_version),
                code=code,
            )
        except RuntimeError as error:
            return self._empty_semantic_result(
                outcome="provider_error",
                index_version=int(index_version),
                code=_safe_provider_code(error),
            )
        except Exception:
            return self._empty_semantic_result(
                outcome="index_unavailable",
                index_version=int(index_version),
                code="knowledge_index_read_failed",
            )

        citation = answer.citations[0]
        return LlmSemanticTestResult(
            outcome="answered",
            provider=_PROVIDER,
            model=self._selector.model,
            index_version=answer.index_version,
            qa_id=_qa_id_from_source(citation.source_identity),
            source_identity=citation.source_identity,
            answer_text=answer.answer,
            code=None,
        )

    def _empty_semantic_result(
        self,
        *,
        outcome: str,
        index_version: int | None,
        code: str,
    ) -> LlmSemanticTestResult:
        return LlmSemanticTestResult(
            outcome=outcome,
            provider=_PROVIDER,
            model=self._selector.model,
            index_version=index_version,
            qa_id=None,
            source_identity=None,
            answer_text=None,
            code=code,
        )


def _safe_provider_code(error: Exception) -> str:
    error_code = str(error)
    if error_code == "gemini_api_key_not_configured":
        return "not_configured"
    if error_code in {"gemini_api_http_401", "gemini_api_http_403"}:
        return "authentication_failed"
    if error_code == "gemini_api_http_404":
        return "model_unavailable"
    if error_code == "gemini_api_http_429":
        return "rate_limited"
    return "provider_error"


def _qa_id_from_source(source_identity: str) -> str | None:
    if _CATALOG_MARKER not in source_identity:
        return None
    qa_id = source_identity.rsplit("#", 1)[-1].strip()
    return qa_id or None


def _ready_index_version() -> int | None:
    with open_knowledge_retrieval_unit_of_work() as unit_of_work:
        return unit_of_work.knowledge.ready_index_version()


def _gateway_factory(selector: CandidateSelectorPort) -> ChromaKnowledgeGateway:
    return ChromaKnowledgeGateway(
        os.getenv("KNOWLEDGE_CHROMA_PATH", "db/chroma_knowledge"),
        llm=selector,
    )


_STORE = LlmApiKeyStore()


def get_llm_configuration_application() -> LlmConfigurationApplication:
    selector = GeminiCandidateSelector(store=_STORE)
    return LlmConfigurationApplication(
        store=_STORE,
        selector=selector,
        ready_index_version=_ready_index_version,
        gateway_factory=_gateway_factory,
    )


__all__ = [
    "CandidateSelectorPort",
    "KnowledgeAnswerGatewayPort",
    "LlmConfigurationApplication",
    "LlmConnectionTestResult",
    "LlmSecretStatus",
    "LlmSemanticTestResult",
    "get_llm_configuration_application",
]

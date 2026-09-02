"""System-admin write-only configuration and safe Gemini test endpoints."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import AdminPrincipal, require_system_admin
from api.schemas.base import BaseResponse
from domains.knowledge_retrieval.knowledge import KnowledgeAnswerUnsupported
from infrastructure.knowledge.chroma_gateway import ChromaKnowledgeGateway
from infrastructure.knowledge.gemini_selector import (
    DEFAULT_GEMINI_MODEL,
    GeminiCandidateSelector,
)
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)
from infrastructure.runtime.llm_api_key_store import LlmApiKeyStatus, LlmApiKeyStore


router = APIRouter(prefix="/api/v1/system/llm", tags=["LLM Configuration"])
_STORE = LlmApiKeyStore()


class LlmApiKeyStatusView(BaseModel):
    configured: bool
    updated_at: datetime | None


class LlmConnectionTestView(BaseModel):
    connected: bool
    provider: str
    model: str
    code: str | None


class LlmSemanticTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)


class LlmSemanticTestView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str
    provider: str
    model: str
    index_version: int | None
    qa_id: str | None
    source_identity: str | None
    answer_text: str | None
    code: str | None


def get_llm_api_key_store() -> LlmApiKeyStore:
    return _STORE


def get_gemini_selector(
    store: LlmApiKeyStore = Depends(get_llm_api_key_store),
) -> GeminiCandidateSelector:
    return GeminiCandidateSelector(store=store)


def _status_view(value: LlmApiKeyStatus) -> LlmApiKeyStatusView:
    return LlmApiKeyStatusView(configured=value.configured, updated_at=value.updated_at)


async def _read_api_key_without_echo(request: Request) -> str:
    try:
        payload: Any = await request.json()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_llm_api_key_payload", "message": "API Key 格式無效"},
        ) from error

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_llm_api_key_payload", "message": "API Key 格式無效"},
        )

    api_key = payload.get("api_key")
    if not isinstance(api_key, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_llm_api_key", "message": "請輸入有效的 API Key"},
        )

    normalized = api_key.strip()
    if len(normalized) < 8 or len(normalized) > 4096:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_llm_api_key", "message": "請輸入有效的 API Key"},
        )
    return normalized


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


def _connection_result(selector: GeminiCandidateSelector) -> LlmConnectionTestView:
    try:
        output = selector("連線測試。只回覆 OK。")
        connected = bool(output.strip())
        return LlmConnectionTestView(
            connected=connected,
            provider="google_ai_studio",
            model=selector.model,
            code=None if connected else "empty_response",
        )
    except TimeoutError:
        code = "timeout"
    except ConnectionError as error:
        code = "rate_limited" if str(error) == "gemini_api_http_429" else "unavailable"
    except RuntimeError as error:
        code = _safe_provider_code(error)

    return LlmConnectionTestView(
        connected=False,
        provider="google_ai_studio",
        model=selector.model or DEFAULT_GEMINI_MODEL,
        code=code,
    )


def _empty_semantic_result(
    selector: GeminiCandidateSelector,
    *,
    outcome: str,
    index_version: int | None,
    code: str,
) -> LlmSemanticTestView:
    return LlmSemanticTestView(
        outcome=outcome,
        provider="google_ai_studio",
        model=selector.model or DEFAULT_GEMINI_MODEL,
        index_version=index_version,
        qa_id=None,
        source_identity=None,
        answer_text=None,
        code=code,
    )


def _qa_id_from_source(source_identity: str) -> str | None:
    marker = "AI客服QA題庫.jsonl#"
    if marker not in source_identity:
        return None
    qa_id = source_identity.rsplit("#", 1)[-1].strip()
    return qa_id or None


def _semantic_result(
    question: str,
    selector: GeminiCandidateSelector,
) -> LlmSemanticTestView:
    with open_knowledge_retrieval_unit_of_work() as unit_of_work:
        index_version = unit_of_work.knowledge.ready_index_version()

    if index_version is None:
        return _empty_semantic_result(
            selector,
            outcome="index_unavailable",
            index_version=None,
            code="knowledge_index_unavailable",
        )

    gateway = ChromaKnowledgeGateway(
        os.getenv("KNOWLEDGE_CHROMA_PATH", "db/chroma_knowledge"),
        llm=selector,
    )
    try:
        answer = gateway.answer(question, int(index_version))
    except KnowledgeAnswerUnsupported:
        return _empty_semantic_result(
            selector,
            outcome="unsupported",
            index_version=int(index_version),
            code="knowledge_answer_unsupported",
        )
    except TimeoutError:
        return _empty_semantic_result(
            selector,
            outcome="provider_error",
            index_version=int(index_version),
            code="timeout",
        )
    except ConnectionError as error:
        code = "rate_limited" if str(error) == "gemini_api_http_429" else "unavailable"
        return _empty_semantic_result(
            selector,
            outcome="provider_error",
            index_version=int(index_version),
            code=code,
        )
    except RuntimeError as error:
        return _empty_semantic_result(
            selector,
            outcome="provider_error",
            index_version=int(index_version),
            code=_safe_provider_code(error),
        )
    except Exception:
        return _empty_semantic_result(
            selector,
            outcome="index_unavailable",
            index_version=int(index_version),
            code="knowledge_index_read_failed",
        )

    citation = answer.citations[0]
    return LlmSemanticTestView(
        outcome="answered",
        provider="google_ai_studio",
        model=selector.model,
        index_version=answer.index_version,
        qa_id=_qa_id_from_source(citation.source_identity),
        source_identity=citation.source_identity,
        answer_text=answer.answer,
        code=None,
    )


@router.get("/api-key/status", response_model=BaseResponse[LlmApiKeyStatusView])
def query_llm_api_key_status(
    _: AdminPrincipal = Depends(require_system_admin),
    store: LlmApiKeyStore = Depends(get_llm_api_key_store),
) -> BaseResponse[LlmApiKeyStatusView]:
    return BaseResponse(data=_status_view(store.status()))


@router.post("/api-key", response_model=BaseResponse[LlmApiKeyStatusView])
async def replace_llm_api_key(
    request: Request,
    _: AdminPrincipal = Depends(require_system_admin),
    store: LlmApiKeyStore = Depends(get_llm_api_key_store),
) -> BaseResponse[LlmApiKeyStatusView]:
    api_key = await _read_api_key_without_echo(request)
    try:
        current_status = store.replace(api_key)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_api_key_storage_unavailable", "message": "API Key 儲存失敗，請稍後再試"},
        ) from error

    request.state.audit_action = "system.llm_api_key.replace"
    request.state.audit_resource_type = "llm_api_key"
    request.state.audit_resource_id = "primary"
    request.state.audit_details = {"configured": current_status.configured}

    return BaseResponse(
        data=_status_view(current_status),
        message="API Key 已更新；系統不提供讀回功能",
    )


@router.post("/connection-test", response_model=BaseResponse[LlmConnectionTestView])
def test_llm_connection(
    request: Request,
    _: AdminPrincipal = Depends(require_system_admin),
    selector: GeminiCandidateSelector = Depends(get_gemini_selector),
) -> BaseResponse[LlmConnectionTestView]:
    result = _connection_result(selector)
    request.state.audit_action = "system.llm.connection_test"
    request.state.audit_resource_type = "llm_provider"
    request.state.audit_resource_id = "google_ai_studio"
    request.state.audit_details = {
        "connected": result.connected,
        "model": result.model,
        "code": result.code,
    }
    message = "Gemini 連線成功" if result.connected else "Gemini 連線測試未通過"
    return BaseResponse(data=result, message=message)


@router.post("/semantic-test", response_model=BaseResponse[LlmSemanticTestView])
def test_llm_semantics(
    body: LlmSemanticTestRequest,
    request: Request,
    _: AdminPrincipal = Depends(require_system_admin),
    selector: GeminiCandidateSelector = Depends(get_gemini_selector),
) -> BaseResponse[LlmSemanticTestView]:
    result = _semantic_result(body.question.strip(), selector)
    request.state.audit_action = "system.llm.semantic_test"
    request.state.audit_resource_type = "llm_provider"
    request.state.audit_resource_id = "google_ai_studio"
    request.state.audit_details = {
        "outcome": result.outcome,
        "model": result.model,
        "index_version": result.index_version,
        "qa_id": result.qa_id,
        "code": result.code,
    }
    message = "Gemini M2 語意測試完成" if result.outcome == "answered" else "Gemini M2 語意測試未產生核准答案"
    return BaseResponse(data=result, message=message)

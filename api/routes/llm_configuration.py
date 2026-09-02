"""System-admin write-only configuration endpoint for the Gemini API key."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from api.dependencies.admin_auth import AdminPrincipal, require_system_admin
from api.schemas.base import BaseResponse
from infrastructure.knowledge.gemini_selector import (
    DEFAULT_GEMINI_MODEL,
    GeminiCandidateSelector,
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
        error_code = str(error)
        code = "rate_limited" if error_code == "gemini_api_http_429" else "unavailable"
    except RuntimeError as error:
        error_code = str(error)
        if error_code == "gemini_api_key_not_configured":
            code = "not_configured"
        elif error_code in {"gemini_api_http_401", "gemini_api_http_403"}:
            code = "authentication_failed"
        elif error_code == "gemini_api_http_404":
            code = "model_unavailable"
        else:
            code = "provider_error"

    return LlmConnectionTestView(
        connected=False,
        provider="google_ai_studio",
        model=selector.model or DEFAULT_GEMINI_MODEL,
        code=code,
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

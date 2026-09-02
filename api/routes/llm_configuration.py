"""System-admin write-only configuration and safe Gemini test endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import AdminPrincipal, require_system_admin
from api.dependencies.llm_configuration import (
    LlmConfigurationApplication,
    LlmSecretStatus,
    get_llm_configuration_application,
)
from api.schemas.base import BaseResponse


router = APIRouter(prefix="/api/v1/system/llm", tags=["LLM Configuration"])


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


def _status_view(value: LlmSecretStatus) -> LlmApiKeyStatusView:
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


@router.get("/api-key/status", response_model=BaseResponse[LlmApiKeyStatusView])
def query_llm_api_key_status(
    _: AdminPrincipal = Depends(require_system_admin),
    application: LlmConfigurationApplication = Depends(get_llm_configuration_application),
) -> BaseResponse[LlmApiKeyStatusView]:
    return BaseResponse(data=_status_view(application.status()))


@router.post("/api-key", response_model=BaseResponse[LlmApiKeyStatusView])
async def replace_llm_api_key(
    request: Request,
    _: AdminPrincipal = Depends(require_system_admin),
    application: LlmConfigurationApplication = Depends(get_llm_configuration_application),
) -> BaseResponse[LlmApiKeyStatusView]:
    api_key = await _read_api_key_without_echo(request)
    try:
        current_status = application.replace_api_key(api_key)
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
    application: LlmConfigurationApplication = Depends(get_llm_configuration_application),
) -> BaseResponse[LlmConnectionTestView]:
    result = application.test_connection()
    request.state.audit_action = "system.llm.connection_test"
    request.state.audit_resource_type = "llm_provider"
    request.state.audit_resource_id = "google_ai_studio"
    request.state.audit_details = {
        "connected": result.connected,
        "model": result.model,
        "code": result.code,
    }
    message = "Gemini 連線成功" if result.connected else "Gemini 連線測試未通過"
    return BaseResponse(data=LlmConnectionTestView(**result.__dict__), message=message)


@router.post("/semantic-test", response_model=BaseResponse[LlmSemanticTestView])
def test_llm_semantics(
    body: LlmSemanticTestRequest,
    request: Request,
    _: AdminPrincipal = Depends(require_system_admin),
    application: LlmConfigurationApplication = Depends(get_llm_configuration_application),
) -> BaseResponse[LlmSemanticTestView]:
    result = application.test_semantics(body.question.strip())
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
    return BaseResponse(data=LlmSemanticTestView(**result.__dict__), message=message)

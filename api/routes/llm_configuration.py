"""System-admin write-only configuration endpoint for the LLM API key."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from api.dependencies.admin_auth import AdminPrincipal, require_system_admin
from api.schemas.base import BaseResponse
from infrastructure.runtime.llm_api_key_store import LlmApiKeyStatus, LlmApiKeyStore


router = APIRouter(prefix="/api/v1/system/llm", tags=["LLM Configuration"])
_STORE = LlmApiKeyStore()


class LlmApiKeyStatusView(BaseModel):
    configured: bool
    updated_at: datetime | None


def get_llm_api_key_store() -> LlmApiKeyStore:
    return _STORE


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

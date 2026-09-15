"""
File: line_service_help.py
Description: 提供客服問答專屬 LIFF API 與頁面路由，支援常見問答檢索與 AI 智慧問答。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.line_identity import get_liff_token_verifier
from api.dependencies.llm_configuration import (
    LlmConfigurationApplication,
    get_llm_configuration_application,
)
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from domains.knowledge_retrieval.qa_catalog import decode_governed_qa
from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
)
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_HELP_PAGE = PROJECT_ROOT / "line" / "static" / "service_help.html"
_NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}

public_router = APIRouter(prefix="/api/v1/line/service-help", tags=["LINE Service Help"])
page_router = APIRouter(tags=["LINE Service Help"])


class FaqItem(BaseModel):
    qa_id: str
    category: str
    tag: str
    question: str
    answer: str
    source_ref: str


class FaqListResponse(BaseModel):
    items: list[FaqItem]
    categories: list[str]


class ServiceHelpAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    interaction_id: str = Field(default="", max_length=191)
    line_id_token: str = Field(default="", max_length=4096)


class ServiceHelpAskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str
    answer_text: str | None = None
    qa_id: str | None = None
    source_identity: str | None = None
    source_version: int | None = None
    index_version: int | None = None
    source_ref: str | None = None
    suggestion: str | None = None
    interaction_id: str | None = None


@page_router.get("/line-service-help", include_in_schema=False)
def service_help_page():
    if not _SERVICE_HELP_PAGE.exists():
        raise HTTPException(status_code=404, detail="Service help page not found")
    return FileResponse(_SERVICE_HELP_PAGE, headers=_NO_CACHE_HEADERS)


@public_router.get("/faq", response_model=BaseResponse[FaqListResponse])
def get_published_faqs() -> BaseResponse[FaqListResponse]:
    items: list[FaqItem] = []
    seen_ids: set[str] = set()

    try:
        with open_knowledge_retrieval_unit_of_work() as unit_of_work:
            raw_items = unit_of_work.knowledge.list_items(100, "published")
    except Exception as error:
        raise typed_http_error(
            503,
            "unavailable",
            "knowledge_catalog_unavailable",
            "常見問答暫時無法讀取，請稍後再試。",
            "line-service-help:faq",
            retryable=True,
        ) from error

    for raw in raw_items:
        try:
            decoded = decode_governed_qa(raw.get("content", ""))
        except Exception as error:
            raise typed_http_error(
                503,
                "internal",
                "knowledge_catalog_invalid",
                "常見問答資料目前無法使用，請稍後再試。",
                "line-service-help:faq",
            ) from error
        if decoded and decoded.qa_id not in seen_ids:
            items.append(
                FaqItem(
                    qa_id=decoded.qa_id,
                    category=decoded.category,
                    tag=decoded.tag,
                    question=decoded.question,
                    answer=decoded.answer,
                    source_ref=decoded.source_ref,
                )
            )
            seen_ids.add(decoded.qa_id)

    categories = list(dict.fromkeys(item.category for item in items))
    return BaseResponse(data=FaqListResponse(items=items, categories=categories))


@public_router.post("/ask", response_model=BaseResponse[ServiceHelpAskResponse])
def ask_service_question(
    body: ServiceHelpAskRequest,
    application: LlmConfigurationApplication = Depends(get_llm_configuration_application),
    liff_verifier=Depends(get_liff_token_verifier),
) -> BaseResponse[ServiceHelpAskResponse]:
    clean_question = body.question.strip()
    interaction_id = _verified_liff_interaction(body, liff_verifier)

    try:
        semantic_result = application.test_semantics(clean_question)
    except Exception as error:
        raise _knowledge_query_unavailable("knowledge_query_unavailable") from error

    if semantic_result.outcome == "answered" and semantic_result.answer_text:
        return BaseResponse(
            data=ServiceHelpAskResponse(
                outcome="answered",
                answer_text=semantic_result.answer_text,
                qa_id=semantic_result.qa_id,
                source_identity=semantic_result.source_identity,
                source_version=semantic_result.source_version,
                index_version=semantic_result.index_version,
                source_ref=semantic_result.source_identity,
                interaction_id=interaction_id,
            ),
            message="AI 助理已由知識庫為您找到解答",
        )

    if semantic_result.outcome == "unsupported":
        return BaseResponse(
            data=ServiceHelpAskResponse(
                outcome="unsupported",
                answer_text=None,
                index_version=semantic_result.index_version,
                suggestion="抱歉，工會知識庫目前尚未收錄與您提問完全相符的標準解答。您可以直接在此 LINE 官方帳號聊天室中留言，工會真人客服專員將親自為您詳細解說！",
                interaction_id=interaction_id,
            ),
            message="未找到相符解答，已引導真人客服",
        )

    if semantic_result.outcome in {"index_unavailable", "provider_error"}:
        raise _knowledge_query_unavailable(
            semantic_result.code or "knowledge_query_unavailable"
        )

    raise _knowledge_query_unavailable("knowledge_query_unavailable")


def _verified_liff_interaction(body: ServiceHelpAskRequest, verifier) -> str | None:
    token = body.line_id_token.strip()
    interaction_id = body.interaction_id.strip()
    if not token and not interaction_id:
        return None
    if not token or not interaction_id:
        raise typed_http_error(
            422,
            "validation",
            "liff_interaction_identity_incomplete",
            "LINE 問答身分資訊不完整，請重新從 LINE 開啟此頁。",
            "line-service-help:interaction",
        )
    try:
        verifier.verify(token)
    except InvalidLiffTokenError as error:
        raise typed_http_error(
            401,
            "forbidden",
            "liff_token_invalid",
            "LINE 登入狀態已失效，請重新從 LINE 開啟此頁。",
            "line-service-help:liff-token-invalid",
        ) from error
    except LiffVerificationUnavailableError as error:
        raise typed_http_error(
            503,
            "unavailable",
            "liff_verification_unavailable",
            "LINE 身分驗證服務暫時無法使用，請稍後再試。",
            "line-service-help:liff-verification-unavailable",
            retryable=True,
        ) from error
    return interaction_id


def _knowledge_query_unavailable(code: str) -> HTTPException:
    return typed_http_error(
        503,
        "unavailable",
        code,
        "AI 智慧問答服務暫時無法使用，請稍後再試。",
        "line-service-help:ask",
        retryable=True,
    )


__all__ = ["page_router", "public_router"]

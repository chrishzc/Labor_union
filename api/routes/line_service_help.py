"""
File: line_service_help.py
Description: 受權限保護的正式題庫查詢與既有 LIFF 入口退役。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from api.dependencies.admin_auth import admin_actor_context, require_admin
from api.dependencies.line_faq_layout import get_service_help_faq_readers
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import AdminPrincipal, has_required_capability
from subsystems.access.integration_capabilities import IntegrationCapability
from subsystems.line.capabilities import LineCapability
from subsystems.knowledge_retrieval.faq_catalog import (
    KnowledgeCatalogUnavailable,
    is_faq_id,
)
from subsystems.line.faq_chat_layout import FaqLayoutUnavailable
from subsystems.line.service_help_application import ServiceHelpFaqReaders

_NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}

public_router = APIRouter(prefix="/api/v1/line/service-help", tags=["LINE Service Help"])
page_router = APIRouter(tags=["LINE Service Help"])
admin_router = APIRouter(prefix="/api/v1/line/faq-layout", tags=["LINE FAQ Layout"])


class FaqItem(BaseModel):
    qa_id: str
    category: str
    category_id: str | None = None
    tag: str
    question: str
    answer: str
    source_ref: str
    version: int


class FaqListResponse(BaseModel):
    items: list[FaqItem]
    categories: list[str]
    next_cursor: str | None = None


_RETIRED_GUIDANCE = "此問答頁面已停用。請回到 LINE 官方帳號聊天室輸入「常見問題」。"


@page_router.get("/line-service-help", include_in_schema=False)
def service_help_page() -> PlainTextResponse:
    return PlainTextResponse(_RETIRED_GUIDANCE, status_code=410, headers=_NO_CACHE_HEADERS)


@public_router.get("/faq", include_in_schema=False)
@public_router.post("/ask", include_in_schema=False)
def retired_service_help() -> None:
    raise typed_http_error(410, "validation", "line_service_help_retired", _RETIRED_GUIDANCE, "line-service-help:retired")


def _require_faq_published_reader(
    request: Request,
    principal: Annotated[AdminPrincipal, Depends(require_admin)],
) -> AdminPrincipal:
    if not any(
        has_required_capability(principal, capability.value)
        for capability in (
            LineCapability.CONFIG_MANAGE,
            IntegrationCapability.KNOWLEDGE_READ,
            IntegrationCapability.KNOWLEDGE_MANAGE,
            IntegrationCapability.KNOWLEDGE_PUBLISH,
        )
    ):
        raise HTTPException(status_code=403, detail="缺少常見問答正式題庫讀取權限")
    request.state.admin_actor = admin_actor_context(principal)
    return principal


@admin_router.get(
    "/published-questions",
    response_model=BaseResponse[FaqListResponse],
    dependencies=[Depends(_require_faq_published_reader)],
)
@public_router.get("/faq", response_model=BaseResponse[FaqListResponse])
def get_published_faqs(
    select_readers: Annotated[Callable[[], ServiceHelpFaqReaders], Depends(get_service_help_faq_readers)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    qa_id: str | None = None,
) -> BaseResponse[FaqListResponse]:
    if qa_id is not None and (not is_faq_id(qa_id) or cursor is not None):
        raise _faq_validation_error("faq_query_invalid", "題目識別或查詢條件無效。")
    try:
        readers = select_readers()
        catalog, layout = readers.catalog, readers.layout
        if catalog is None:
            raise KnowledgeCatalogUnavailable("knowledge_catalog_unavailable")
        if qa_id is None:
            page = catalog.page(cursor, limit)
            questions, next_cursor = page.items, page.next_cursor
        else:
            question = catalog.get(qa_id)
            questions, next_cursor = ((question,) if question else ()), None
        category_names = layout.category_names() if layout is not None and questions else {}
    except ValueError as error:
        if str(error) != "faq_cursor_invalid":
            raise
        raise _faq_validation_error("faq_cursor_invalid", "常見問答的頁面游標無效。") from error
    except (KnowledgeCatalogUnavailable, FaqLayoutUnavailable) as error:
        code = (
            "faq_layout_unavailable"
            if isinstance(error, FaqLayoutUnavailable)
            else "knowledge_catalog_unavailable"
        )
        raise typed_http_error(
            503,
            "unavailable",
            code,
            "常見問答暫時無法讀取，請稍後再試。",
            "line-service-help:faq",
            retryable=True,
        ) from error

    items = [
        FaqItem(
            qa_id=item.qa_id,
            category=category_names.get(item.category_id, item.category),
            category_id=item.category_id,
            tag=item.tag,
            question=item.question,
            answer=item.answer,
            source_ref=item.source_ref,
            version=item.source_version,
        )
        for item in questions
    ]
    categories = list(dict.fromkeys(item.category for item in items))
    return BaseResponse(data=FaqListResponse(items=items, categories=categories, next_cursor=next_cursor))


def _faq_validation_error(code: str, message: str) -> HTTPException:
    return typed_http_error(422, "validation", code, message, "line-service-help:faq")

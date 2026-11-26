"""Administration and read-only shared categories for the LINE FAQ layout."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_knowledge_manager,
    require_line_configuration_manager,
)
from api.dependencies.line_faq_layout import get_faq_chat_layout_application
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from domains.line.faq_chat_layout import FAQ_ID_PATTERN, FaqIssue, FaqLayoutInvalid, FaqPreview
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.knowledge_retrieval.faq_catalog import KnowledgeCatalogUnavailable
from subsystems.line.faq_chat_layout import (
    FaqCategoryNotPublished,
    FaqChatLayoutApplication,
    FaqLayoutIdempotencyConflict,
    FaqLayoutRevisionConflict,
    FaqLayoutState,
    FaqLayoutUnavailable,
    FaqOperationReceipt,
)


class _FaqValidationRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def validated(request: Request):
            try:
                return await handle(request)
            except RequestValidationError as error:
                issues = tuple(
                    FaqIssue("invalid_field", ".".join(map(str, item["loc"])))
                    for item in error.errors()
                )
                raise _invalid(request, issues) from error

        return validated


router = APIRouter(
    prefix="/api/v1/line/faq-layout", tags=["LINE FAQ Layout"], route_class=_FaqValidationRoute,
)
knowledge_router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Retrieval"])

_Application = Annotated[FaqChatLayoutApplication, Depends(get_faq_chat_layout_application)]
_Manager = Annotated[AdminPrincipal, Depends(require_line_configuration_manager)]
_OperationKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_CategoryId = Annotated[str, Field(pattern=f"^{FAQ_ID_PATTERN}$")]


class _RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _RevisionBody(_RequestBody):
    expected_revision: int = Field(ge=0, le=(2**64 - 2))


class _CategoryBody(_RevisionBody):
    name: str


class _DraftBody(_RevisionBody):
    layout: dict[str, Any]


class _DraftPreview(_RequestBody):
    mode: Literal["draft"]
    category_id: _CategoryId
    layout: dict[str, Any]


class _PublishedPreview(_RequestBody):
    mode: Literal["published"]
    category_id: _CategoryId


class _CategoryOption(BaseModel):
    category_id: str
    name: str


class _SharedCategories(BaseModel):
    categories: list[_CategoryOption]


@router.get("", response_model=BaseResponse[FaqLayoutState])
def query_layout(request: Request, principal: _Manager, application: _Application):
    with _typed_errors(request):
        return BaseResponse[FaqLayoutState](data=application.query(admin_actor_context(principal)))


@router.post("/preview", response_model=BaseResponse[FaqPreview])
def preview_layout(
    request: Request,
    body: Annotated[_DraftPreview | _PublishedPreview, Body(discriminator="mode")],
    principal: _Manager,
    application: _Application,
):
    with _typed_errors(request):
        result = application.preview(
            admin_actor_context(principal),
            body.category_id,
            draft=body.layout if isinstance(body, _DraftPreview) else None,
        )
        return BaseResponse[FaqPreview](data=result)


@router.post("/categories", response_model=BaseResponse[FaqOperationReceipt], response_model_exclude_none=True)
def create_category(
    request: Request, body: _CategoryBody, principal: _Manager, application: _Application,
    idempotency_key: _OperationKey, correlation_id: _CorrelationHeader,
):
    with _typed_errors(request):
        identity = _write_identity(request, principal, idempotency_key, correlation_id)
        return BaseResponse[FaqOperationReceipt](data=application.create_category(
            body.name, body.expected_revision, *identity,
        ))


@router.put("/draft", response_model=BaseResponse[FaqOperationReceipt], response_model_exclude_none=True)
def save_draft(
    request: Request, body: _DraftBody, principal: _Manager, application: _Application,
    idempotency_key: _OperationKey, correlation_id: _CorrelationHeader,
):
    with _typed_errors(request):
        identity = _write_identity(request, principal, idempotency_key, correlation_id)
        return BaseResponse[FaqOperationReceipt](data=application.save_draft(
            body.layout, body.expected_revision, *identity,
        ))


@router.post("/publish", response_model=BaseResponse[FaqOperationReceipt], response_model_exclude_none=True)
def publish_layout(
    request: Request, body: _RevisionBody, principal: _Manager, application: _Application,
    idempotency_key: _OperationKey, correlation_id: _CorrelationHeader,
):
    with _typed_errors(request):
        identity = _write_identity(request, principal, idempotency_key, correlation_id)
        return BaseResponse[FaqOperationReceipt](data=application.publish(body.expected_revision, *identity))


@router.get(
    "/operations/{operation_id:path}",
    response_model=BaseResponse[FaqOperationReceipt],
    response_model_exclude_none=True,
)
def read_operation(
    request: Request, operation_id: str, idempotency_key: _OperationKey,
    principal: _Manager, application: _Application,
):
    with _typed_errors(request):
        key = _operation_key(idempotency_key)
        if operation_id != key.value:
            raise FaqLayoutInvalid(FaqIssue("operation_key_mismatch", "header.idempotency-key"))
        receipt = application.operation(admin_actor_context(principal), key)
        if receipt is None:
            raise _http_error(request, 404, "not_found", "faq_layout_operation_not_found", "尚無可讀取的操作回執。")
        return BaseResponse[FaqOperationReceipt](data=receipt)


@knowledge_router.get("/faq-categories", response_model=BaseResponse[_SharedCategories])
def read_knowledge_categories(
    request: Request,
    application: _Application,
    _principal: Annotated[AdminPrincipal, Depends(require_knowledge_manager)],
):
    with _typed_errors(request):
        return BaseResponse[_SharedCategories](data=_SharedCategories(categories=[
            _CategoryOption(category_id=category_id, name=name)
            for category_id, name in application.category_names().items()
        ]))


def _operation_key(text: str) -> IdempotencyKey:
    try:
        return IdempotencyKey(text)
    except ValueError as error:
        raise FaqLayoutInvalid(FaqIssue("invalid_field", "header.idempotency-key")) from error


def _write_identity(
    request: Request, principal: AdminPrincipal, key: str, correlation_id: str,
) -> tuple[ActorContext, IdempotencyKey, CorrelationId]:
    if not getattr(request.state, "correlation_id_provided", True):
        raise FaqLayoutInvalid(FaqIssue("required", "header.x-correlation-id"))
    return admin_actor_context(principal), _operation_key(key), CorrelationId(correlation_id)


def _http_error(
    request: Request, status: int, category: str, code: str, message: str, *, retryable: bool = False,
):
    return typed_http_error(
        status, category, code, message, getattr(request.state, "correlation_id", "line-faq-layout"),
        retryable=retryable,
    )


def _invalid(request: Request, issues: tuple[FaqIssue, ...]):
    error = _http_error(request, 422, "validation", "faq_layout_invalid", "請檢查聊天室版面欄位。")
    messages = {
        "duplicate_category_name": "已有相同名稱的分類。",
        "faq_question_not_published": "題目目前未發布。",
        "faq_line_reply_too_long": "答案加上來源與固定提示後超過 LINE 上限，請先縮短題庫答案。",
        "published_question_required": "每張卡片至少要有一題已發布的問答。",
        "title_required": "發布前請填寫卡片標題。",
        "empty_layout": "發布前請新增分類與題目。",
        "category_identity_changed": "儲存版面時無法新增、刪除、改名或移動分類。",
    }
    error.detail["error"]["field_errors"] = [
        {"field": issue.field, "code": issue.code, "message": messages.get(issue.code, "欄位格式不符合契約。")}
        for issue in issues
    ]
    return error


@contextmanager
def _typed_errors(request: Request):
    try:
        yield
    except FaqLayoutInvalid as error:
        raise _invalid(request, error.issues) from error
    except FaqCategoryNotPublished as error:
        raise _http_error(request, 404, "not_found", "faq_category_not_published", "此分類尚未發布。") from error
    except FaqLayoutRevisionConflict as error:
        response = _http_error(request, 409, "conflict", "faq_layout_revision_conflict", "版面已更新，請重新讀取。")
        response.detail["error"]["current_version"] = error.current_revision
        raise response from error
    except FaqLayoutIdempotencyConflict as error:
        raise _http_error(
            request, 409, "idempotency_mismatch", "faq_layout_idempotency_conflict", "本次操作與原操作內容不同。",
        ) from error
    except FaqLayoutUnavailable as error:
        raise _http_error(
            request, 503, "unavailable", "faq_layout_unavailable", "聊天室版面暫時無法使用。", retryable=True,
        ) from error
    except KnowledgeCatalogUnavailable as error:
        raise _http_error(
            request, 503, "unavailable", "knowledge_catalog_unavailable", "常見問答暫時無法讀取。", retryable=True,
        ) from error

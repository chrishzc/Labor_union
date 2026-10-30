"""Authenticated zero-write LINE message previews; no delivery/provider composition."""

from dataclasses import asdict
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from api.dependencies.admin_auth import admin_actor_context, require_line_configuration_reader
from api.dependencies.line_runtime import get_line_configuration_application
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.line_message_preview import (
    PreviewDescriptorView, PreviewOptionPageView, RenderPreviewRequest, RenderPreviewView,
)
from infrastructure.mysql.line_message_preview_repository import open_message_preview_reader
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.message_configuration import LineMessageConfigurationError
from subsystems.line.message_preview import LineMessagePreviewApplication, MessagePreviewNotFound

router = APIRouter(prefix="/api/v1/line/message-previews", tags=["LINE Message Previews"])


@lru_cache(maxsize=1)
def get_message_preview_application():
    from infrastructure.line.table_image_renderer import render_table_image
    return LineMessagePreviewApplication(get_line_configuration_application(), open_message_preview_reader, render_table_image)


def _query(call):
    try:
        return call()
    except MessagePreviewNotFound as error:
        raise typed_http_error(404, "not_found", "line_message_preview_not_found", "找不到所選訊息、案件或月嫂，請重新查詢。", "line-message-preview") from error
    except (LineMessageConfigurationError, ValueError) as error:
        raise typed_http_error(422, "validation", "line_message_preview_invalid", "文案或必要變數不完整，請確認內容後再試。", "line-message-preview") from error
    except Exception as error:
        raise typed_http_error(503, "unavailable", "line_message_preview_unavailable", "訊息預覽暫時無法載入，請稍後再試。", "line-message-preview", retryable=True) from error


@router.get("/catalog", response_model=BaseResponse[list[PreviewDescriptorView]])
def catalog(response: Response, principal: AdminPrincipal = Depends(require_line_configuration_reader)):
    response.headers["Cache-Control"] = "no-store"
    result = _query(lambda: get_message_preview_application().catalog(admin_actor_context(principal)))
    return BaseResponse(data=[asdict(item) for item in result])


@router.get("/subjects", response_model=BaseResponse[PreviewOptionPageView])
def subjects(response: Response, kind: Literal["case", "staff"], search: str = Query(default="", max_length=100),
             after: str | None = Query(default=None, min_length=1, max_length=191),
             principal: AdminPrincipal = Depends(require_line_configuration_reader)):
    response.headers["Cache-Control"] = "no-store"
    if kind == "staff" and after is not None and (not after.isascii() or not after.isdigit() or len(after) > 18):
        raise typed_http_error(422, "validation", "line_preview_cursor_invalid", "分頁位置無效，請重新查詢。", "line-message-preview")
    result = _query(lambda: get_message_preview_application().options(kind, search, after, admin_actor_context(principal)))
    return BaseResponse(data=asdict(result))


@router.post("/preview", response_model=BaseResponse[RenderPreviewView])
def render(payload: RenderPreviewRequest, response: Response,
           principal: AdminPrincipal = Depends(require_line_configuration_reader)):
    response.headers["Cache-Control"] = "no-store"
    result = _query(lambda: get_message_preview_application().render(payload.id, payload.content, payload.case_no,
                                                                    payload.staff_id, admin_actor_context(principal), sample=payload.data_source == "sample"))
    return BaseResponse(data=asdict(result))

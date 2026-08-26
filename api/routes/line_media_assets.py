"""
File: line_media_assets.py
Description: 提供已認證管理員 owner-scoped Rich Menu 圖片 metadata 唯讀查詢。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Path, Query

from api.dependencies.admin_auth import require_line_configuration_reader
from api.error_contracts import typed_http_error
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.line_media_assets import (
    RichMenuMediaAssetDetailResponse,
    RichMenuMediaAssetPageResponse,
    RichMenuMediaAssetPageView,
    RichMenuMediaAssetView,
)
from infrastructure.mysql.line_media_asset_query_repository import (
    MySqlLineRichMenuMediaAssetQueryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.media_asset_contracts import (
    RichMenuMediaAssetDetailQuery,
    RichMenuMediaAssetListQuery,
)
from subsystems.line.ports import LineRichMenuMediaAssetQueryRepositoryPort

router = APIRouter(
    prefix="/api/v1/line/media-assets/rich-menu",
    tags=["LINE Rich Menu Media"],
)

_QUERY_RESPONSES = {
    401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證。"},
    403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權讀取 Rich Menu 圖片。"},
    422: {"model": GlobalTypedErrorResponseView, "description": "查詢欄位不符合公開契約。"},
    503: {"model": GlobalTypedErrorResponseView, "description": "Rich Menu 圖片查詢暫時無法完成。"},
}


def get_line_rich_menu_media_asset_query_repository(
) -> Iterator[LineRichMenuMediaAssetQueryRepositoryPort]:
    connection = get_connection()
    try:
        yield MySqlLineRichMenuMediaAssetQueryRepository(connection)
    finally:
        connection.close()


Repository = Annotated[
    LineRichMenuMediaAssetQueryRepositoryPort,
    Depends(get_line_rich_menu_media_asset_query_repository),
]


@router.get(
    "",
    response_model=RichMenuMediaAssetPageResponse,
    responses=_QUERY_RESPONSES,
)
def list_rich_menu_media_assets(
    repository: Repository,
    menu_definition_id: str = Query(
        min_length=1,
        max_length=100,
        pattern=r"^\S(?:.*\S)?$",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _principal: AdminPrincipal = Depends(require_line_configuration_reader),
) -> RichMenuMediaAssetPageResponse:
    try:
        result = repository.list(
            RichMenuMediaAssetListQuery(menu_definition_id, page, page_size)
        )
        return RichMenuMediaAssetPageResponse(
            data=RichMenuMediaAssetPageView(
                items=[_view(item) for item in result.items],
                page=result.page,
                page_size=result.page_size,
                total=result.total,
                total_pages=result.total_pages,
            )
        )
    except Exception as exc:
        _query_unavailable(exc)


@router.get(
    "/{asset_id}",
    response_model=RichMenuMediaAssetDetailResponse,
    responses={
        **_QUERY_RESPONSES,
        404: {"model": GlobalTypedErrorResponseView, "description": "找不到此選單的 Rich Menu 圖片。"},
    },
)
def get_rich_menu_media_asset(
    repository: Repository,
    asset_id: int = Path(gt=0),
    menu_definition_id: str = Query(
        min_length=1,
        max_length=100,
        pattern=r"^\S(?:.*\S)?$",
    ),
    _principal: AdminPrincipal = Depends(require_line_configuration_reader),
) -> RichMenuMediaAssetDetailResponse:
    try:
        item = repository.get(
            RichMenuMediaAssetDetailQuery(menu_definition_id, asset_id)
        )
        if item is None:
            raise typed_http_error(
                404,
                "not_found",
                "line_rich_menu_media_asset_not_found",
                "找不到此選單的 Rich Menu 圖片。",
                "line-rich-menu-media-query",
            )
        return RichMenuMediaAssetDetailResponse(data=_view(item))
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            raise
        _query_unavailable(exc)


def _view(item) -> RichMenuMediaAssetView:
    return RichMenuMediaAssetView(
        asset_id=item.asset_id,
        menu_definition_id=item.menu_definition_id,
        original_filename=item.original_filename,
        mime_type=item.mime_type,
        file_size=item.file_size,
        sha256=item.sha256,
        width=item.width,
        height=item.height,
        created_at=item.created_at,
        deleted_at=item.deleted_at,
        selectable=item.selectable,
        business_reason=item.business_reason,
        asset_version=item.asset_version.value,
    )


def _query_unavailable(exc: Exception) -> NoReturn:
    raise typed_http_error(
        503,
        "unavailable",
        "line_rich_menu_media_asset_query_unavailable",
        "Rich Menu 圖片查詢暫時無法完成。",
        "line-rich-menu-media-query",
        retryable=True,
    ) from exc


__all__ = ["router"]

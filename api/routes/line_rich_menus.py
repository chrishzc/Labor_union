"""
================================================================================
檔案名稱: api/routes/line_rich_menus.py
功能說明: LINE 下方選單 API，提供圖片上傳、預覽、發布、發布紀錄與失敗重試
================================================================================
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_configuration_reader,
    require_line_manager,
    require_line_menu_publisher,
    require_line_viewer,
)
from api.dependencies.line_runtime import (
    get_line_configuration_application,
    get_line_rich_menu_application,
    get_line_wakeup_publisher,
)
from api.schemas.base import BaseResponse
from api.schemas.line_config import LineMenusConfig, RichMenuDefinition
from api.schemas.line_rich_menus import (
    RichMenuPublicationRetryRequest,
    RichMenuPublishRequest,
)
from domains.line.configuration import LineConfigurationKind
from domains.line.identities import (
    LineRichMenuPublicationId,
)
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_store import read_config
from subsystems.line.rich_menu_publication_workflow import (
    RichMenuPublicationConflictError,
    RichMenuPublicationNotFoundError,
    create_publication_job,
    get_publication,
    list_publications,
    retry_publication,
)
from subsystems.line.rich_menu_application import LineRichMenuNotFoundError
from subsystems.line.rich_menu_contracts import (
    LineRichMenuPublicationQuery,
    QueueLineRichMenuPublicationCommand,
    RetryLineRichMenuPublicationCommand,
)
from subsystems.line.media_archive import (
    MAX_UPLOAD_BYTES,
    MediaAssetNotFoundError,
    MediaValidationError,
    delete_media_asset,
    read_media_asset,
    render_rich_menu_image,
    store_uploaded_rich_menu_image,
)


router = APIRouter(
    prefix="/api/v1/line/rich-menus",
    tags=["LINE Rich Menu"],
    dependencies=[Depends(require_line_viewer)],
)


def _publication_error(exc: Exception) -> None:
    if isinstance(exc, (RichMenuPublicationNotFoundError, MediaAssetNotFoundError)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, LineRichMenuNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (RichMenuPublicationConflictError, RuntimeError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, (MediaValidationError, ValueError)):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


def _menu(menu_id: str) -> RichMenuDefinition:
    config = read_config("line_menus", LineMenusConfig)
    menu = next((item for item in config.menus if item.id == menu_id), None)
    if not menu:
        raise HTTPException(status_code=404, detail="找不到 Rich Menu")
    return menu


@router.post("/preview", response_class=Response)
def preview_rich_menu(payload: RichMenuDefinition):
    try:
        if payload.appearance.image_mode == "uploaded" and payload.appearance.image_asset_id:
            _, image = read_media_asset(payload.appearance.image_asset_id)
        else:
            image = render_rich_menu_image(payload.model_dump(mode="json"))
    except (MediaValidationError, MediaAssetNotFoundError) as exc:
        _publication_error(exc)
    return Response(content=image, media_type="image/jpeg")


@router.post(
    "/{menu_id}/images",
    response_model=BaseResponse[dict],
    dependencies=[Depends(require_line_manager)],
)
async def upload_rich_menu_image(
    menu_id: str,
    request: Request,
    image: UploadFile = File(...),
):
    menu = _menu(menu_id)
    content = await image.read(MAX_UPLOAD_BYTES + 1)
    try:
        asset = store_uploaded_rich_menu_image(
            content,
            menu_id=menu_id,
            original_filename=image.filename or "rich-menu-image",
            expected_width=menu.size.width,
            expected_height=menu.size.height,
            created_by_admin_user_id=request.state.admin_principal.id,
        )
    except (MediaValidationError, MediaAssetNotFoundError) as exc:
        _publication_error(exc)
    request.state.audit_action = "line.rich_menu.image.upload"
    request.state.audit_resource_type = "media_asset"
    request.state.audit_resource_id = str(asset["id"])
    return BaseResponse(
        data={
            key: asset.get(key)
            for key in (
                "id",
                "original_filename",
                "mime_type",
                "file_size",
                "sha256",
                "width",
                "height",
                "created_at",
            )
        },
        message="Rich Menu 圖片已安全保存",
    )


@router.delete(
    "/images/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_line_manager)],
)
def remove_rich_menu_image(asset_id: int, request: Request):
    config = read_config("line_menus", LineMenusConfig)
    if any(menu.appearance.image_asset_id == asset_id for menu in config.menus):
        raise HTTPException(status_code=409, detail="此圖片仍被 Rich Menu 草稿引用")
    try:
        delete_media_asset(asset_id)
    except (MediaAssetNotFoundError, MediaValidationError) as exc:
        _publication_error(exc)
    request.state.audit_action = "line.rich_menu.image.delete"
    request.state.audit_resource_type = "media_asset"
    request.state.audit_resource_id = str(asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/publications", response_model=BaseResponse[dict])
def publication_list(
    menu_id: str | None = None,
    publication_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
):
    try:
        statuses = ()
        if publication_status:
            from domains.line.rich_menu import LineRichMenuPublicationStatus

            statuses = (LineRichMenuPublicationStatus(publication_status),)
        items = get_line_rich_menu_application().list(
            LineRichMenuPublicationQuery(statuses=tuple(sorted(statuses, key=lambda item: item.value)), page_size=100),
            admin_actor_context(principal),
        )
    except ValueError as exc:
        _publication_error(exc)
    if menu_id:
        items = tuple(item for item in items if item.menu_definition_id == menu_id)
    offset = (page - 1) * page_size
    selected = items[offset : offset + page_size]
    return BaseResponse(
        data={
            "items": [_publication_snapshot(item) for item in selected],
            "page": page,
            "page_size": page_size,
            "total": len(items),
            "total_pages": max(1, (len(items) + page_size - 1) // page_size),
        }
    )


@router.get("/publications/{publication_id}", response_model=BaseResponse[dict])
def publication_detail(
    publication_id: int,
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
):
    try:
        result = get_line_rich_menu_application().get(
            LineRichMenuPublicationId(publication_id),
            admin_actor_context(principal),
        )
    except LineRichMenuNotFoundError as exc:
        _publication_error(exc)
    return BaseResponse(data=_publication_snapshot(result))


@router.post(
    "/publications/{publication_id}/retry",
    response_model=BaseResponse[dict],
)
def publication_retry(
    publication_id: int,
    payload: RichMenuPublicationRetryRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_menu_publisher),
):
    suffix = uuid4().hex
    try:
        result = get_line_rich_menu_application().retry(
            RetryLineRichMenuPublicationCommand(
                LineRichMenuPublicationId(publication_id),
                admin_actor_context(principal),
                payload.reason.strip() or "管理員重新發布 Rich Menu",
                IdempotencyKey(payload.idempotency_key.strip() or f"rich-menu-retry:{suffix}"),
                CorrelationId(payload.correlation_id.strip() or f"rich-menu-retry:{suffix}"),
            )
        )
    except (LineRichMenuNotFoundError, RuntimeError, ValueError) as exc:
        _publication_error(exc)
    request.state.audit_action = "line.rich_menu.publication.retry"
    request.state.audit_resource_type = "line_rich_menu_publication"
    request.state.audit_resource_id = str(publication_id)
    request.state.audit_details = {"reason": payload.reason.strip()} if payload.reason.strip() else None
    _publish_wakeup()
    return BaseResponse(data=_publication_snapshot(result), message="發布工作已重新排入")


@router.post(
    "/{menu_id}/publish",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_202_ACCEPTED,
)
def publish_rich_menu(
    menu_id: str,
    payload: RichMenuPublishRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_menu_publisher),
):
    suffix = uuid4().hex
    actor = admin_actor_context(principal)
    try:
        configuration = get_line_configuration_application().get(
            LineConfigurationKind.RICH_MENUS,
            actor,
        )
        result = get_line_rich_menu_application().queue(
            QueueLineRichMenuPublicationCommand(
                menu_id,
                configuration.revision,
                actor,
                IdempotencyKey(payload.idempotency_key.strip() or f"rich-menu-publish:{suffix}"),
                CorrelationId(payload.correlation_id.strip() or f"rich-menu-publish:{suffix}"),
            )
        )
    except (LineRichMenuNotFoundError, RuntimeError, ValueError) as exc:
        _publication_error(exc)
    request.state.audit_action = "line.rich_menu.publish"
    request.state.audit_resource_type = "line_rich_menu_publication"
    request.state.audit_resource_id = str(result.publication_id.value)
    request.state.audit_details = {"reason": payload.reason.strip()} if payload.reason.strip() else None
    _publish_wakeup()
    return BaseResponse(data=_publication_snapshot(result), message="Rich Menu 發布工作已建立")


def _publication_snapshot(item):
    return {
        "id": item.publication_id.value,
        "menu_definition_id": item.menu_definition_id,
        "configuration_revision": item.configuration_revision.value,
        "status": item.status.value,
    }


def _publish_wakeup():
    try:
        get_line_wakeup_publisher().publish()
    except Exception:
        pass

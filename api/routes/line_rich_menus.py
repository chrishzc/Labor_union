"""
File: line_rich_menus.py
Description: 提供 Rich Menu 零寫入發布預覽、媒體與既有發布相容端點。
"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Request, UploadFile, status
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
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.line_config import LineMenusConfig, RichMenuDefinition
from api.schemas.line_rich_menus import (
    RichMenuPublishPreviewRequest,
    RichMenuPublishPreviewResponse,
    RichMenuPublishPreviewResult,
    RichMenuPublicationPageView,
    RichMenuPublicationMutationResult,
    RichMenuPublicationQueueResponse,
    RichMenuPublicationRetryRequest,
    RichMenuPublicationRetryResponse,
    RichMenuPublicationView,
    RichMenuPublishRequest,
)
from domains.line.configuration import LineConfigurationKind
from domains.line.identities import LineConfigurationRevision, LineRichMenuPublicationId
from domains.line.rich_menu import LineRichMenuPublicationStatus
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_store import read_config
from subsystems.line.rich_menu_publication_workflow import (
    RichMenuPublicationConflictError,
    RichMenuPublicationNotFoundError,
    create_publication_preview,
    get_publication_step_receipts,
    list_publication_page,
    queue_publication,
    validate_publication_preview,
)
from subsystems.line.rich_menu_application import LineRichMenuNotFoundError
from subsystems.line.rich_menu_contracts import (
    LineRichMenuPublicationQuery,
    PreviewLineRichMenuCommand,
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

_PUBLICATION_QUERY_ERROR_RESPONSES = {
    401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證。"},
    403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權讀取 Rich Menu 發布紀錄。"},
    422: {"model": GlobalTypedErrorResponseView, "description": "查詢欄位不符合公開契約。"},
    503: {"model": GlobalTypedErrorResponseView, "description": "Rich Menu 發布查詢暫時無法完成。"},
}

_SAFE_CONFLICT_CODES = frozenset(
    {
        "line_rich_menu_command_idempotency_conflict",
        "line_rich_menu_configuration_revision_conflict",
        "line_rich_menu_current_preview_required",
        "line_rich_menu_idempotency_conflict",
        "line_rich_menu_preview_confirmation_conflict",
        "line_rich_menu_receipt_reference_invalid",
        "line_rich_menu_receipt_result_missing",
        "line_rich_menu_retry_state_conflict",
        "line_rich_menu_preview_stale",
    }
)


def _publication_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (RichMenuPublicationNotFoundError, MediaAssetNotFoundError)):
        raise typed_http_error(
            404, "not_found", "rich_menu_publication_not_found",
            "找不到 Rich Menu 發布紀錄。", "rich-menu-publication",
        ) from exc
    if isinstance(exc, LineRichMenuNotFoundError):
        raise typed_http_error(
            404, "not_found", "rich_menu_publication_not_found",
            "找不到可發布的 Rich Menu。", "rich-menu-publication",
        ) from exc
    if isinstance(exc, RichMenuPublicationConflictError):
        status_code = 401 if exc.code == "authenticated_admin_required" else 409
        message = (
            "需要已登入的管理員。"
            if exc.code == "authenticated_admin_required"
            else "Rich Menu 發布請求與目前狀態衝突。"
        )
        raise typed_http_error(
            status_code,
            "unauthorized" if status_code == 401 else "conflict",
            exc.code,
            message,
            "rich-menu-publication",
        ) from exc
    if isinstance(exc, RuntimeError):
        code = exc.args[0] if len(exc.args) == 1 else None
        if isinstance(code, str) and code in _SAFE_CONFLICT_CODES:
            raise typed_http_error(
                409,
                "conflict",
                code,
                "Rich Menu 發布請求與目前狀態衝突。",
                "rich-menu-publication",
            ) from exc
    if isinstance(exc, (MediaValidationError, ValueError)):
        raise typed_http_error(
            422, "validation", "rich_menu_publication_invalid",
            "Rich Menu 發布資料未通過驗證。", "rich-menu-publication",
        ) from exc
    raise typed_http_error(
        503, "unavailable", "rich_menu_publication_unavailable",
        "Rich Menu 發布暫時無法完成。", "rich-menu-publication",
        retryable=True,
    ) from exc


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
    dependencies=[Depends(require_line_menu_publisher)],
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
    dependencies=[Depends(require_line_menu_publisher)],
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


@router.get(
    "/publications",
    response_model=BaseResponse[RichMenuPublicationPageView],
    responses=_PUBLICATION_QUERY_ERROR_RESPONSES,
)
def publication_list(
    menu_id: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=191,
            pattern=r"^\S(?:.*\S)?$",
        ),
    ] = None,
    publication_status: Annotated[
        LineRichMenuPublicationStatus | None,
        Query(alias="status"),
    ] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
):
    try:
        statuses = () if publication_status is None else (publication_status,)
        offset = (page - 1) * page_size
        result_page = list_publication_page(
            LineRichMenuPublicationQuery(
                menu_definition_id=menu_id,
                statuses=tuple(sorted(statuses, key=lambda item: item.value)),
                page_size=page_size,
            ),
            offset=offset,
            actor=admin_actor_context(principal),
        )
    except ValueError as exc:
        raise typed_http_error(
            503,
            "unavailable",
            "rich_menu_publication_query_unavailable",
            "Rich Menu 發布查詢結果無法安全提供。",
            "rich-menu-publication-query",
        ) from exc
    except RuntimeError as exc:
        raise typed_http_error(
            503,
            "unavailable",
            "rich_menu_publication_query_unavailable",
            "Rich Menu 發布查詢暫時無法完成。",
            "rich-menu-publication-query",
            retryable=True,
        ) from exc
    except Exception as exc:
        raise typed_http_error(
            503,
            "unavailable",
            "rich_menu_publication_query_unavailable",
            "Rich Menu 發布查詢暫時無法完成。",
            "rich-menu-publication-query",
            retryable=True,
        ) from exc
    try:
        views = [_publication_view(item) for item in result_page.items]
    except (AttributeError, TypeError, ValueError) as exc:
        raise typed_http_error(
            503,
            "unavailable",
            "rich_menu_publication_query_unavailable",
            "Rich Menu 發布結果未通過安全驗證。",
            "rich-menu-publication-query",
        ) from exc
    return BaseResponse[RichMenuPublicationPageView](
        data=RichMenuPublicationPageView(
            items=views,
            page=page,
            page_size=page_size,
            total=result_page.total,
            total_pages=max(1, (result_page.total + page_size - 1) // page_size),
        )
    )


@router.get(
    "/publications/{publication_id}",
    response_model=BaseResponse[RichMenuPublicationView],
    responses={
        **_PUBLICATION_QUERY_ERROR_RESPONSES,
        404: {"model": GlobalTypedErrorResponseView, "description": "找不到 Rich Menu 發布紀錄。"},
    },
)
def publication_detail(
    publication_id: Annotated[int, Path(gt=0)],
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
):
    try:
        result = get_line_rich_menu_application().get(
            LineRichMenuPublicationId(publication_id),
            admin_actor_context(principal),
        )
    except LineRichMenuNotFoundError as exc:
        raise typed_http_error(
            404,
            "not_found",
            "rich_menu_publication_not_found",
            "找不到 Rich Menu 發布紀錄。",
            "rich-menu-publication-query",
        ) from exc
    except ValueError as exc:
        raise typed_http_error(
            503,
            "unavailable",
            "rich_menu_publication_query_unavailable",
            "Rich Menu 發布紀錄無法安全提供。",
            "rich-menu-publication-query",
        ) from exc
    except Exception as exc:
        raise typed_http_error(
            503,
            "unavailable",
            "rich_menu_publication_query_unavailable",
            "Rich Menu 發布查詢暫時無法完成。",
            "rich-menu-publication-query",
            retryable=True,
        ) from exc
    try:
        receipts = get_publication_step_receipts(
            LineRichMenuPublicationId(publication_id),
            admin_actor_context(principal),
        )
        view = _publication_view(result, receipts)
    except (AttributeError, TypeError, ValueError) as exc:
        raise typed_http_error(
            503,
            "unavailable",
            "rich_menu_publication_query_unavailable",
            "Rich Menu 發布結果未通過安全驗證。",
            "rich-menu-publication-query",
        ) from exc
    except Exception as exc:
        raise typed_http_error(
            503,
            "unavailable",
            "rich_menu_publication_query_unavailable",
            "Rich Menu 發布查詢暫時無法完成。",
            "rich-menu-publication-query",
            retryable=True,
        ) from exc
    return BaseResponse[RichMenuPublicationView](data=view)


@router.post(
    "/publications/{publication_id}/retry",
    response_model=RichMenuPublicationRetryResponse,
)
def publication_retry(
    publication_id: Annotated[int, Path(gt=0)],
    payload: RichMenuPublicationRetryRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_menu_publisher),
):
    try:
        result = get_line_rich_menu_application().retry(
            RetryLineRichMenuPublicationCommand(
                LineRichMenuPublicationId(publication_id),
                admin_actor_context(principal),
                payload.reason,
                IdempotencyKey(payload.idempotency_key),
                CorrelationId(payload.correlation_id),
            )
        )
    except (LineRichMenuNotFoundError, RuntimeError, ValueError) as exc:
        _publication_error(exc)
    request.state.audit_action = "line.rich_menu.publication.retry"
    request.state.audit_resource_type = "line_rich_menu_publication"
    request.state.audit_resource_id = str(publication_id)
    request.state.audit_details = {"reason": payload.reason}
    _publish_wakeup()
    return RichMenuPublicationRetryResponse(data=_publication_mutation_result(result))


@router.post(
    "/{menu_id}/publish-preview",
    response_model=RichMenuPublishPreviewResponse,
)
def create_rich_menu_publish_preview(
    menu_id: Annotated[str, Path(min_length=1, max_length=191)],
    principal: AdminPrincipal = Depends(require_line_menu_publisher),
) -> RichMenuPublishPreviewResponse:
    preview_request = RichMenuPublishPreviewRequest(
        menu_id=menu_id,
        actor_id=principal.id,
    )
    actor = admin_actor_context(principal)
    try:
        configuration = get_line_configuration_application().get(
            LineConfigurationKind.RICH_MENUS,
            actor,
        )
        candidate = get_line_rich_menu_application().preview(
            PreviewLineRichMenuCommand(
                menu_definition_id=preview_request.menu_id,
                configuration_revision=configuration.revision,
                correlation_id=CorrelationId(
                    f"rich-menu-preview:{preview_request.actor_id}:"
                    f"{configuration.revision.value}"
                ),
            ),
            actor,
        )
    except LineRichMenuNotFoundError as error:
        _raise_preview_error(
            404,
            "not_found",
            "rich_menu_preview_not_found",
            "找不到可預覽的 Rich Menu。",
        )
    except RuntimeError as error:
        _raise_preview_error(
            409,
            "conflict",
            "rich_menu_preview_stale",
            "Rich Menu 設定已變更，請重新查詢後再預覽。",
        )
    except ValueError as error:
        _raise_preview_error(
            422,
            "validation",
            "rich_menu_preview_invalid",
            "Rich Menu 預覽資料未通過驗證。",
        )
    except Exception as error:
        _raise_preview_error(
            503,
            "unavailable",
            "rich_menu_preview_unavailable",
            "Rich Menu 預覽暫時無法完成。",
            retryable=True,
        )
    try:
        result = create_publication_preview(
            preview_request.menu_id,
            preview_request.actor_id,
            config_revision=configuration.revision.value,
            candidate=candidate,
        )
        data = RichMenuPublishPreviewResult.model_validate(result)
    except Exception as error:
        _raise_preview_error(
            500,
            "internal",
            "rich_menu_preview_contract_invalid",
            "Rich Menu 預覽結果無法安全提供。",
        )
    return RichMenuPublishPreviewResponse(data=data)


@router.post(
    "/{menu_id}/publish",
    response_model=RichMenuPublicationQueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def publish_rich_menu(
    menu_id: Annotated[str, Path(min_length=1, max_length=191)],
    payload: RichMenuPublishRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_menu_publisher),
):
    actor = admin_actor_context(principal)
    try:
        preview = validate_publication_preview(
            menu_id,
            preview_id=payload.preview_id,
            previewed_by_admin_user_id=principal.id,
        )
        result = queue_publication(
            QueueLineRichMenuPublicationCommand(
                menu_definition_id=menu_id,
                configuration_revision=LineConfigurationRevision(
                    int(preview["config_revision"])
                ),
                actor=actor,
                idempotency_key=IdempotencyKey(payload.idempotency_key),
                correlation_id=CorrelationId(payload.correlation_id),
                preview_id=payload.preview_id,
                preview_config_revision=preview["config_revision"],
                preview_config_fingerprint=preview["config_fingerprint"],
                previewed_by_admin_user_id=principal.id,
            ),
            reason=payload.reason,
        )
    except (LineRichMenuNotFoundError, RuntimeError, ValueError) as exc:
        _publication_error(exc)
    request.state.audit_details = {"reason": payload.reason}
    _publish_wakeup()
    return RichMenuPublicationQueueResponse(data=_publication_mutation_result(result))


def _publication_mutation_result(item) -> RichMenuPublicationMutationResult:
    return RichMenuPublicationMutationResult.model_validate(
        {
            "id": item.publication_id.value,
            "menu_definition_id": item.menu_definition_id,
            "configuration_revision": item.configuration_revision.value,
            "status": item.status,
        }
    )


def _publication_view(item, receipts=()) -> RichMenuPublicationView:
    """從 Domain snapshot 建立 closed projection，拒絕 raw provider 欄位穿透。"""

    return RichMenuPublicationView.model_validate(
        {
            **_publication_mutation_result(item).model_dump(),
            "step_receipts": [
                {
                    "step": receipt.step.value,
                    "acknowledged_at": receipt.acknowledged_at,
                }
                for receipt in receipts
            ],
        }
    )


def _publish_wakeup():
    try:
        get_line_wakeup_publisher().publish()
    except Exception:
        pass


def _raise_preview_error(
    status_code: int,
    category: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "category": category,
                "code": code,
                "message": message,
                "field_errors": [],
                "domain_blockers": [],
                "retryable": retryable,
                "correlation_id": "rich-menu-publish-preview",
                "current_version": None,
            }
        },
    )

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response
from pymysql.err import OperationalError, ProgrammingError
from infrastructure.mysql import mysql_adapter as db_service
from infrastructure.mysql.admin_command_repository import AdminCommandRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.orders.lifecycle_control_read_projection import (
    OrderLifecycleControlReadNotFoundError,
    get_order_lifecycle_control_state,
)
from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_calendar_detail import (
    OrderCalendarDetailApplication,
    get_order_calendar_detail_application,
)
from api.dependencies.order_detail import (
    OrderDetailApplication,
    get_order_detail_application,
)
from api.dependencies.order_summary import (
    OrderSummaryApplication,
    get_order_summary_application,
)
from api.dependencies.form_management import (
    FormManagementQueryApplication,
    get_form_management_query_application,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.order_calendar_detail import OrderCalendarDetailView
from api.schemas.order_detail import OrderDetailView
from api.schemas.order_summary import (
    OrderSummaryItemView,
    OrderSummaryPageView,
)
from api.schemas.form_management import (
    FormManagementCaseContextView,
    FormManagementStatisticsView,
)
from api.schemas.orders import (
    OrderFullUpdateRequest,
    ClientNameApplyRequest,
    ClientNamePreviewRequest,
    OrderStatusUpdateRequest,
    ScheduleCalculationRequest,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.calendar_detail_query import (
    OrderCalendarDetailContractError,
    OrderCalendarDetailNotFoundError,
)
from subsystems.orders.detail_query import (
    OrderDetailContractError,
    OrderDetailNotFoundError,
)
from subsystems.orders.summary_query import (
    OrderSummaryContractError,
    OrderSummaryQueryRequest,
)
from subsystems.orders.form_management_query import (
    FormManagementCaseNotFoundError,
    FormManagementQueryContractError,
)
from subsystems.orders import client_name_maintenance



router = APIRouter(prefix="/api/v1/orders", tags=["Orders 訂單管理"])


def _json_safe(value: Any) -> Any:
    """Recursively materialize one service result without flattening its shape."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        materialized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("lifecycle result mapping keys must be strings")
            materialized[key] = _json_safe(item)
        return materialized
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        if not isfinite(value):
            raise TypeError("lifecycle result contains a non-finite float")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError("lifecycle result contains an unsupported value")


@router.get("")
def get_all_orders() -> None:
    """Retire the unbounded list endpoint in favour of the summary projection."""
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_order_full_list_endpoint_retired",
            "replacement": "/api/v1/orders/summaries",
            "message": "Use the bounded cursor-based order summary endpoint.",
        },
    )


# Kept cohesive so one endpoint visibly maps every typed query failure to HTTP.
@router.get(
    "/summaries",
    response_model=BaseResponse[OrderSummaryPageView],
)
def get_order_summaries(
    response: Response,
    page_size: int = Query(50, ge=1, le=200),
    after_case_no: str | None = Query(None, min_length=1, max_length=50),
    query_text: str | None = Query(None, min_length=1, max_length=100),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderSummaryApplication = Depends(
        get_order_summary_application
    ),
):
    del principal
    try:
        page = application.query(
            OrderSummaryQueryRequest(page_size, after_case_no, query_text)
        )
    except OrderSummaryContractError as error:
        raise typed_http_error(
            409,
            "conflict",
            "order_summary_projection_invalid",
            "訂單摘要根事實無法產生一致投影。",
            "order-summary-query",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise _order_summary_database_error(error) from error
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            "order_summary_query_invalid",
            "訂單摘要查詢條件不正確。",
            "order-summary-query",
        ) from error
    except Exception as error:
        raise internal_query_error(
            "order_summary_query_internal_error",
            "訂單摘要查詢失敗。",
            "order-summary-query",
        ) from error
    etag = f'"{page.etag}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if _etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return BaseResponse(
        data=_order_summary_page_view(page),
        message="成功取得訂單摘要清單",
    )


@router.get(
    "/form-management-statistics",
    response_model=BaseResponse[FormManagementStatisticsView],
)
def get_form_management_statistics(
    principal: AdminPrincipal = Depends(require_system_admin),
    application: FormManagementQueryApplication = Depends(
        get_form_management_query_application
    ),
):
    del principal
    try:
        return BaseResponse(
            data=FormManagementStatisticsView.model_validate(
                application.statistics(), from_attributes=True
            ),
            message="成功取得表單全域統計",
        )
    except FormManagementQueryContractError as error:
        raise typed_http_error(
            409,
            "conflict",
            "form_management_statistics_projection_invalid",
            "表單全域統計無法產生一致投影。",
            "form-management-statistics",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise _form_management_database_error(error) from error


@router.get(
    "/{case_no}/form-management-context",
    response_model=BaseResponse[FormManagementCaseContextView],
)
def get_form_management_case_context(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: FormManagementQueryApplication = Depends(
        get_form_management_query_application
    ),
):
    del principal
    try:
        return BaseResponse(
            data=FormManagementCaseContextView.model_validate(
                application.case_context(case_no), from_attributes=True
            ),
            message="成功取得表單案件資料",
        )
    except FormManagementCaseNotFoundError as error:
        raise typed_http_error(
            404,
            "not_found",
            "form_management_case_not_found",
            "表單案件資料不存在。",
            "form-management-case-context",
        ) from error
    except FormManagementQueryContractError as error:
        raise typed_http_error(
            409,
            "conflict",
            "form_management_case_projection_invalid",
            "表單案件資料無法產生一致投影。",
            "form-management-case-context",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise _form_management_database_error(error) from error


def _order_summary_page_view(page) -> OrderSummaryPageView:
    return OrderSummaryPageView(
        items=[
            OrderSummaryItemView.model_validate(item, from_attributes=True)
            for item in page.items
        ],
        next_cursor=page.next_cursor,
        etag=page.etag,
    )


def _etag_matches(candidate: str | None, current: str) -> bool:
    if not candidate:
        return False
    tokens = {token.strip() for token in candidate.split(",")}
    return "*" in tokens or current in {
        token.removeprefix("W/") for token in tokens
    }


def _order_summary_database_error(error):
    mysql_code = int(error.args[0]) if error.args else 0
    retryable = mysql_code in {1205, 1213}
    return typed_http_error(
        503 if retryable else 500,
        "unavailable" if retryable else "internal",
        (
            "order_summary_query_temporarily_unavailable"
            if retryable
            else "order_summary_query_database_error"
        ),
        "訂單摘要查詢暫時無法完成。",
        "order-summary-query",
        retryable=retryable,
    )


def _form_management_database_error(error):
    mysql_code = int(error.args[0]) if error.args else 0
    retryable = mysql_code in {1205, 1213}
    return typed_http_error(
        503 if retryable else 500,
        "unavailable" if retryable else "internal",
        "form_management_query_temporarily_unavailable" if retryable else "form_management_query_database_error",
        "表單資料查詢暫時無法完成。",
        "form-management-query",
        retryable=retryable,
    )


# Kept cohesive so one endpoint visibly maps every typed query failure to HTTP.
@router.get(
    "/{case_no}/calendar-detail",
    response_model=BaseResponse[OrderCalendarDetailView],
)
def get_order_calendar_detail(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderCalendarDetailApplication = Depends(
        get_order_calendar_detail_application
    ),
):
    del principal
    try:
        detail = application.query(case_no)
        return BaseResponse(
            data=OrderCalendarDetailView(
                case_no=detail.case_no,
                service_mode=detail.service_mode,
            ),
            message="成功取得訂單固定排休條款",
        )
    except OrderCalendarDetailNotFoundError as error:
        raise typed_http_error(
            404,
            "not_found",
            "order_calendar_detail_not_found",
            "找不到指定訂單的排班條款。",
            "order-calendar-detail-query",
        ) from error
    except OrderCalendarDetailContractError as error:
        raise typed_http_error(
            409,
            "conflict",
            "order_calendar_detail_projection_invalid",
            "訂單固定排休根事實不是支援的正式值。",
            "order-calendar-detail-query",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise _order_calendar_detail_database_error(error) from error
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            "order_calendar_detail_query_invalid",
            "訂單排班條款查詢條件不正確。",
            "order-calendar-detail-query",
        ) from error
    except Exception as error:
        raise internal_query_error(
            "order_calendar_detail_query_internal_error",
            "訂單排班條款查詢失敗。",
            "order-calendar-detail-query",
        ) from error


def _order_calendar_detail_database_error(error):
    mysql_code = int(error.args[0]) if error.args else 0
    retryable = mysql_code in {1205, 1213}
    return typed_http_error(
        503 if retryable else 500,
        "unavailable" if retryable else "internal",
        (
            "order_calendar_detail_temporarily_unavailable"
            if retryable
            else "order_calendar_detail_database_error"
        ),
        "訂單排班條款查詢暫時無法完成。",
        "order-calendar-detail-query",
        retryable=retryable,
    )


@router.get("/{case_no}", response_model=BaseResponse[OrderDetailView])
def get_order_by_case_no(
    case_no: str = Path(..., min_length=1, max_length=50, description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderDetailApplication = Depends(get_order_detail_application),
):
    """Return the declared detail projection for one selected order."""
    del principal
    try:
        detail = application.query(case_no)
        return BaseResponse(
            data=OrderDetailView.model_validate(detail, from_attributes=True),
            message="成功取得單筆訂單資訊",
        )
    except OrderDetailNotFoundError as error:
        raise typed_http_error(
            404, "not_found", "order_detail_not_found", "找不到指定訂單。",
            "order-detail-query",
        ) from error
    except OrderDetailContractError as error:
        raise typed_http_error(
            409, "conflict", "order_detail_projection_invalid",
            "訂單完整資料無法產生一致投影。", "order-detail-query",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise _order_detail_database_error(error) from error
    except ValueError as error:
        raise typed_http_error(
            422, "validation", "order_detail_query_invalid", "訂單查詢條件不正確。",
            "order-detail-query",
        ) from error
    except Exception as error:
        raise internal_query_error(
            "order_detail_query_internal_error",
            "訂單資料查詢失敗。",
            "order-detail-query",
        ) from error


def _order_detail_database_error(error):
    mysql_code = int(error.args[0]) if error.args else 0
    retryable = mysql_code in {1205, 1213}
    return typed_http_error(
        503 if retryable else 500,
        "unavailable" if retryable else "internal",
        "order_detail_query_temporarily_unavailable" if retryable else "order_detail_query_database_error",
        "訂單完整資料查詢暫時無法完成。",
        "order-detail-query",
        retryable=retryable,
    )


@router.get(
    "/{case_no}/lifecycle-control-state",
    response_model=BaseResponse[dict[str, Any]],
)
def get_order_lifecycle_control_state_route(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Return the authoritative, read-only lifecycle control snapshot."""
    del principal
    try:
        result = get_order_lifecycle_control_state(case_no)
        materialized = _json_safe(result)
        if not isinstance(materialized, dict):
            raise TypeError("lifecycle control state must be an object")
        return BaseResponse(
            data=materialized,
            message="成功取得訂單生命週期控制狀態",
        )
    except OrderLifecycleControlReadNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise internal_query_error(
            "order_lifecycle_query_internal_error",
            "訂單生命週期狀態查詢失敗。",
            "order-lifecycle-query",
        ) from error


@router.post("/{case_no}/client-name/preview", response_model=BaseResponse[Dict[str, Any]])
def preview_client_name_change(req: ClientNamePreviewRequest, case_no: str = Path(..., description="案件編號"), principal: AdminPrincipal = Depends(require_system_admin)):
    del principal
    connection = get_connection()
    try:
        result = client_name_maintenance.preview(AdminCommandRepository(connection), case_no, req.client_name.strip())
        return BaseResponse(data=result, message="已產生客戶姓名變更預覽")
    except Exception as error:
        raise internal_query_error("client_name_preview_internal_error", "客戶姓名預覽失敗。", "client-name-preview") from error
    finally:
        connection.close()


@router.post("/{case_no}/client-name/apply", response_model=BaseResponse[Dict[str, Any]])
def apply_client_name_change(req: ClientNameApplyRequest, case_no: str = Path(..., description="案件編號"), idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=191), principal: AdminPrincipal = Depends(require_system_admin)):
    connection = get_connection()
    try:
        result = client_name_maintenance.apply(AdminCommandRepository(connection), case_no, req.client_name.strip(), req.preview_fingerprint, idempotency_key, principal.username, req.reason)
        return BaseResponse(data=result, message="已套用客戶姓名變更")
    except ValueError as error:
        connection.rollback()
        code = str(error)
        raise HTTPException(status_code=409 if code in {"stale_preview", "idempotency_key_conflict"} else 404 if code == "client_not_found" else 422, detail={"code": code}) from error
    except Exception as error:
        connection.rollback()
        raise internal_query_error("client_name_apply_internal_error", "客戶姓名套用失敗。", "client-name-apply") from error
    finally:
        connection.close()


@router.put("/{case_no}/full-details", deprecated=True)
def update_order_full_details(case_no: str = Path(..., description="案件編號")):
    raise HTTPException(status_code=410, detail={"code": "legacy_order_full_details_endpoint_retired", "preview_path": f"/api/v1/orders/{case_no}/client-name/preview", "apply_path": f"/api/v1/orders/{case_no}/client-name/apply"})

@router.put("/{case_no}/status", response_model=BaseResponse[bool])
def update_order_status(
    req: OrderStatusUpdateRequest,
    case_no: str = Path(..., description="案件編號")
):
    """Retired generic status writer; callers must use typed commands."""
    del req
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_order_status_endpoint_retired",
            "case_no": case_no,
            "replacement_commands": [
                {
                    "command": "preview_order_cancellation",
                    "method": "POST",
                    "path": f"/api/v1/orders/{case_no}/cancellation/preview",
                },
                {
                    "command": "apply_order_cancellation",
                    "method": "POST",
                    "path": f"/api/v1/orders/{case_no}/cancellation/apply",
                },
                {
                    "command": "preview_actual_start",
                    "method": "POST",
                    "path": f"/api/v1/orders/{case_no}/actual-start/preview",
                },
                {
                    "command": "apply_actual_start",
                    "method": "POST",
                    "path": f"/api/v1/orders/{case_no}/actual-start/apply",
                },
                {
                    "command": "change_order_terms",
                    "method": "POST",
                    "path": f"/api/v1/orders/{case_no}/terms/preview",
                },
            ],
        },
    )






@router.post(
    "/{case_no}/cancel",
    response_model=BaseResponse[dict[str, Any]],
    deprecated=True,
)
def cancel_order_lock_for_case_no(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired single-step writer; cancellation requires Preview then Apply."""
    del principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_order_cancellation_endpoint_retired",
            "case_no": case_no,
            "preview_path": (
                f"/api/v1/orders/{case_no}/cancellation/preview"
            ),
            "apply_path": f"/api/v1/orders/{case_no}/cancellation/apply",
        },
    )


@router.post(
    "/{case_no}/actual-start/reconfirm",
    response_model=BaseResponse[dict[str, Any]],
    deprecated=True,
)
def reconfirm_order_actual_start_route(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired writer; Actual Start requires typed Preview then Apply."""
    del principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_actual_start_reconfirmation_endpoint_retired",
            "case_no": case_no,
            "preview_path": f"/api/v1/orders/{case_no}/actual-start/preview",
            "apply_path": f"/api/v1/orders/{case_no}/actual-start/apply",
        },
    )


@router.post(
    "/{case_no}/holds",
    response_model=BaseResponse[dict[str, Any]],
    deprecated=True,
)
def activate_order_lifecycle_hold(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired control; anomalies expose root-fact recovery actions."""
    del principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_human_hold_endpoint_retired",
            "case_no": case_no,
            "replacement": "Anomalies typed root-fact recovery actions",
        },
    )


@router.post(
    "/{case_no}/holds/{hold_key}/release",
    response_model=BaseResponse[dict[str, Any]],
    deprecated=True,
)
def release_order_lifecycle_hold(
    case_no: str = Path(..., description="案件編號"),
    hold_key: str = Path(..., description="暫停識別鍵"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired control; historical hold rows remain read-only."""
    del principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_human_hold_endpoint_retired",
            "case_no": case_no,
            "hold_key": hold_key,
            "replacement": "Anomalies typed root-fact recovery actions",
        },
    )


@router.post(
    "/{case_no}/lifecycle-corrections",
    response_model=BaseResponse[dict[str, Any]],
    deprecated=True,
)
def correct_order_lifecycle_route(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired writer; lifecycle status is derived from root facts."""
    del principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_lifecycle_correction_endpoint_retired",
            "case_no": case_no,
            "replacement": "Owning Domain root-fact Preview/Apply",
        },
    )


@router.post(
    "/{case_no}/assignment-synchronization/preview",
    response_model=BaseResponse[Dict[str, Any]],
    deprecated=True,
)
def preview_order_assignment_synchronization(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired endpoint; Assignment Plan owns formal staffing Preview."""
    del principal
    raise _retired_assignment_sync_error(case_no)


@router.post(
    "/{case_no}/assignment-synchronization/apply",
    response_model=BaseResponse[Dict[str, Any]],
    deprecated=True,
)
def apply_order_assignment_synchronization(
    case_no: str = Path(..., description="案件編號"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired endpoint; Assignment Plan owns formal staffing Apply."""
    del principal
    raise _retired_assignment_sync_error(case_no)


def _retired_assignment_sync_error(case_no: str) -> HTTPException:
    return HTTPException(
        status_code=410,
        detail={
            "code": "legacy_assignment_synchronization_endpoint_retired",
            "case_no": case_no,
            "query_path": f"/api/v1/orders/{case_no}/assignment-plan",
            "preview_path": (
                f"/api/v1/orders/{case_no}/assignment-plan/preview"
            ),
            "apply_path": f"/api/v1/orders/{case_no}/assignment-plan/apply",
        },
    )

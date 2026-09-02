"""
File: orders_core_stage_projection.py
Description: 提供待辦看板 Beta 十三核心階段的獨立唯讀 HTTP endpoint。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.orders_stage_projection import (
    OrdersStageProjectionApplication,
    get_orders_stage_projection_application,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.orders_core_stage_projection import OrderCoreStageTimelinePageView
from domains.orders.lifecycle import OrderLifecycleScope
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.core_stage_filter_query import (
    CoreStageProjectionFilterQuery,
    CoreStageSubstatusCode,
    query_core_stage_page,
)
from subsystems.orders.core_stage_projection_query import (
    CoreStageBranchType,
    CoreStageCode,
    CoreStageProjectionContractError,
)
from subsystems.orders.stage_projection_query import OrderStageProjectionContractError


router = APIRouter(prefix="/api/orders", tags=["Orders Core Stage Timeline Beta"])


@router.get(
    "/core-stage-timelines",
    response_model=BaseResponse[OrderCoreStageTimelinePageView],
    responses={
        304: {"description": "十三核心階段投影自上次查詢後未變更"},
        401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證"},
        403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權查詢訂單核心階段"},
        409: {"model": GlobalTypedErrorResponseView, "description": "核心階段投影根事實不一致"},
        422: {"model": GlobalTypedErrorResponseView, "description": "查詢條件不符合公�z�契約"},
        500: {"model": GlobalTypedErrorResponseView, "description": "核心階段投影查詢失敗"},
        503: {"model": GlobalTypedErrorResponseView, "description": "核心階段根事實暫時無法使用"},
    },
)
def get_order_core_stage_timelines(
    response: Response,
    page_size: int = Query(50, ge=1, le=200),
    after_case_no: str | None = Query(None, min_length=1, max_length=50),
    lifecycle_scope: OrderLifecycleScope = Query(OrderLifecycleScope.ALL),
    stage: Annotated[CoreStageCode | None, Query()] = None,
    substatus_code: Annotated[CoreStageSubstatusCode | None, Query()] = None,
    case_no_search: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    blocker_only: Annotated[bool, Query()] = False,
    warning_only: Annotated[bool, Query()] = False,
    branch_type: Annotated[CoreStageBranchType | None, Query()] = None,
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrdersStageProjectionApplication = Depends(get_orders_stage_projection_application),
):
    del principal
    try:
        page = query_core_stage_page(
            application,
            CoreStageProjectionFilterQuery(
                page_size=page_size,
                after_case_no=after_case_no,
                lifecycle_scope=lifecycle_scope,
                stage=stage,
                substatus_code=substatus_code,
                case_no_search=case_no_search,
                blocker_only=blocker_only,
                warning_only=warning_only,
                branch_type=branch_type,
            ),
        )
        view = OrderCoreStageTimelinePageView.model_validate(page, from_attributes=True)
    except (OrderStageProjectionContractError, CoreStageProjectionContractError) as error:
        raise typed_http_error(
            409,
            "conflict",
            "order_core_stage_projection_invalid",
            "訂單十三核心階段根事實無法產生一致投影。",
            "orders-core-stage-projection-query",
        ) from error
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            "order_core_stage_projection_query_invalid",
            "訂單核心階段查詢條件不正確。",
            "orders-core-stage-projection-query",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise typed_http_error(
            503,
            "unavailable",
            "order_core_stage_projection_source_unavailable",
            "訂單核心階段根事實目前無法讀取。",
            "orders-core-stage-projection-query",
        ) from error
    except Exception as error:
        raise internal_query_error(
            "order_core_stage_projection_internal_error",
            "訂單核心階段查詢失敗。",
            "orders-core-stage-projection-query",
        ) from error

    etag = f'"{page.etag}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if if_none_match is not None and if_none_match.strip() == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return BaseResponse(data=view, message="成功取得訂單十三核心階段投影")


__all__ = ["router"]

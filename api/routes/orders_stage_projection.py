"""
File: orders_stage_projection.py
Description: 提供 bounded Orders 七階段、十一作業步驟、Government Subsidy 與完全結案唯讀 HTTP endpoint。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_government_subsidy_projection import (
    get_order_government_subsidy_projection_repository,
)
from api.dependencies.orders_stage_projection import OrdersStageProjectionApplication, get_orders_stage_projection_application
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.order_government_subsidy_projection import (
    OrderGovernmentSubsidyProjectionPageView,
)
from api.schemas.orders_stage_projection import (
    OrderOperationalTimelinePageView,
    OrderTerminalAggregatePageView,
)
from domains.orders.lifecycle import OrderLifecycleScope
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.government_subsidy_projection_query import (
    GovernmentSubsidyProjectionContractError,
    GovernmentSubsidyProjectionQuery,
    GovernmentSubsidySubstatusCode,
    query_government_subsidy_projection_page,
)
from subsystems.orders.stage_projection_query import OrderStageProjectionContractError, StageProjectionQuery
from subsystems.orders.terminal_aggregate_query import (
    TerminalAggregateContractError,
    TerminalAggregateQuery,
    query_terminal_aggregate_page,
)


router = APIRouter(prefix="/api/orders", tags=["Orders Operational Timeline"])


@router.get(
    "/operational-timelines",
    response_model=BaseResponse[OrderOperationalTimelinePageView],
    responses={
        304: {"description": "投影自上次查詢後未變更"},
        401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證"},
        403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權查詢訂單階段"},
        409: {"model": GlobalTypedErrorResponseView, "description": "投影根事實不一致"},
        422: {"model": GlobalTypedErrorResponseView, "description": "查詢條件不符合公開契約"},
        500: {"model": GlobalTypedErrorResponseView, "description": "投影查詢失敗"},
        503: {"model": GlobalTypedErrorResponseView, "description": "投影資料暫時無法使用"},
    },
)
def get_order_operational_timelines(
    response: Response,
    page_size: int = Query(50, ge=1, le=200),
    after_case_no: str | None = Query(None, min_length=1, max_length=50),
    lifecycle_scope: OrderLifecycleScope = Query(OrderLifecycleScope.ALL),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrdersStageProjectionApplication = Depends(get_orders_stage_projection_application),
):
    del principal
    try:
        page = application.query(StageProjectionQuery(page_size, after_case_no, lifecycle_scope))
        view = OrderOperationalTimelinePageView.model_validate(page, from_attributes=True)
    except OrderStageProjectionContractError as error:
        raise typed_http_error(409, "conflict", "order_stage_projection_invalid", "訂單階段根事實無法產生一致投影。", "orders-stage-projection-query") from error
    except ValueError as error:
        raise typed_http_error(422, "validation", "order_stage_projection_query_invalid", "訂單階段查詢條件不正確。", "orders-stage-projection-query") from error
    except (OperationalError, ProgrammingError) as error:
        raise typed_http_error(503, "unavailable", "order_stage_projection_source_unavailable", "訂單階段根事實目前無法讀取。", "orders-stage-projection-query") from error
    except Exception as error:
        raise internal_query_error("order_stage_projection_internal_error", "訂單階段查詢失敗。", "orders-stage-projection-query") from error
    etag = f'"{page.etag}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if if_none_match is not None and if_none_match.strip() == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return BaseResponse(data=view, message="成功取得訂單七階段與作業歷程")


@router.get(
    "/government-subsidy-projections",
    response_model=BaseResponse[OrderGovernmentSubsidyProjectionPageView],
    responses={
        304: {"description": "Government Subsidy 訂單投影自上次查詢後未變更"},
        401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證"},
        403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權查詢補助投影"},
        409: {"model": GlobalTypedErrorResponseView, "description": "補助 owner facts 無法形成一致投影"},
        422: {"model": GlobalTypedErrorResponseView, "description": "補助查詢條件不符合公開契約"},
        500: {"model": GlobalTypedErrorResponseView, "description": "補助投影查詢失敗"},
        503: {"model": GlobalTypedErrorResponseView, "description": "補助 owner facts 暫時無法使用"},
    },
)
def get_order_government_subsidy_projections(
    response: Response,
    page_size: int = Query(50, ge=1, le=200),
    after_case_no: str | None = Query(None, min_length=1, max_length=50),
    case_no_search: str | None = Query(None, min_length=1, max_length=50),
    substatus_code: GovernmentSubsidySubstatusCode | None = Query(None),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrdersStageProjectionApplication = Depends(get_orders_stage_projection_application),
    repository=Depends(get_order_government_subsidy_projection_repository),
):
    del principal
    try:
        page = query_government_subsidy_projection_page(
            application,
            repository,
            GovernmentSubsidyProjectionQuery(
                page_size=page_size,
                after_case_no=after_case_no,
                case_no_search=case_no_search,
                substatus_code=substatus_code,
            ),
        )
        view = OrderGovernmentSubsidyProjectionPageView.model_validate(
            page,
            from_attributes=True,
        )
    except (
        OrderStageProjectionContractError,
        GovernmentSubsidyProjectionContractError,
    ) as error:
        raise typed_http_error(
            409,
            "conflict",
            "order_government_subsidy_projection_invalid",
            "Government Subsidy owner facts 無法產生一致的訂單唯讀投影。",
            "order-government-subsidy-projection-query",
        ) from error
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            "order_government_subsidy_projection_query_invalid",
            "Government Subsidy 訂單投影查詢條件不正確。",
            "order-government-subsidy-projection-query",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise typed_http_error(
            503,
            "unavailable",
            "order_government_subsidy_projection_source_unavailable",
            "Government Subsidy owner facts 目前無法讀取。",
            "order-government-subsidy-projection-query",
        ) from error
    except Exception as error:
        raise internal_query_error(
            "order_government_subsidy_projection_internal_error",
            "Government Subsidy 訂單投影查詢失敗。",
            "order-government-subsidy-projection-query",
        ) from error

    etag = f'"{page.etag}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if if_none_match is not None and if_none_match.strip() == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return BaseResponse(data=view, message="成功取得訂單 Government Subsidy 唯讀投影")


@router.get(
    "/terminal-aggregates",
    response_model=BaseResponse[OrderTerminalAggregatePageView],
    responses={
        401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證"},
        403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權查詢完全結案投影"},
        409: {"model": GlobalTypedErrorResponseView, "description": "完全結案 owner facts 無法形成一致投影"},
        422: {"model": GlobalTypedErrorResponseView, "description": "完全結案查詢條件不符合公開契約"},
        500: {"model": GlobalTypedErrorResponseView, "description": "完全結案投影查詢失敗"},
        503: {"model": GlobalTypedErrorResponseView, "description": "完全結案 owner facts 暫時無法使用"},
    },
)
def get_order_terminal_aggregates(
    page_size: int = Query(50, ge=1, le=200),
    after_case_no: str | None = Query(None, min_length=1, max_length=50),
    case_no_search: str | None = Query(None, min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrdersStageProjectionApplication = Depends(get_orders_stage_projection_application),
    repository=Depends(get_order_government_subsidy_projection_repository),
):
    del principal
    try:
        page = query_terminal_aggregate_page(
            application,
            repository,
            TerminalAggregateQuery(
                page_size=page_size,
                after_case_no=after_case_no,
                case_no_search=case_no_search,
            ),
        )
        view = OrderTerminalAggregatePageView.model_validate(page, from_attributes=True)
    except (
        OrderStageProjectionContractError,
        GovernmentSubsidyProjectionContractError,
        TerminalAggregateContractError,
    ) as error:
        raise typed_http_error(
            409,
            "conflict",
            "order_terminal_aggregate_invalid",
            "完全結案所需 owner facts 無法產生一致投影。",
            "order-terminal-aggregate-query",
        ) from error
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            "order_terminal_aggregate_query_invalid",
            "完全結案查詢條件不正確。",
            "order-terminal-aggregate-query",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise typed_http_error(
            503,
            "unavailable",
            "order_terminal_aggregate_source_unavailable",
            "完全結案所需 owner facts 目前無法讀取。",
            "order-terminal-aggregate-query",
        ) from error
    except Exception as error:
        raise internal_query_error(
            "order_terminal_aggregate_internal_error",
            "完全結案投影查詢失敗。",
            "order-terminal-aggregate-query",
        ) from error
    return BaseResponse(data=view, message="成功取得訂單完全結案唯讀投影")


__all__ = ["router"]

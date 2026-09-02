"""
File: orders_core_stage_projection.py
Description: 提供待辦看板 Beta 十三核心階段、Government Subsidy side lane 與歷史 evidence 的唯讀 HTTP endpoint。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.historical_order_adoption_evidence import (
    get_historical_order_adoption_evidence_repository,
)
from api.dependencies.order_government_subsidy_projection import (
    get_order_government_subsidy_projection_repository,
)
from api.dependencies.orders_stage_projection import (
    OrdersStageProjectionApplication,
    get_orders_stage_projection_application,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.historical_order_adoption_evidence import HistoricalOrderAdoptionEvidenceView
from api.schemas.order_government_subsidy_projection import (
    OrderGovernmentSubsidyProjectionPageView,
)
from api.schemas.orders_core_stage_projection import OrderCoreStageTimelinePageView
from domains.orders.lifecycle import OrderLifecycleScope
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.core_stage_filter_query import (
    CoreStageProjectionFilterQuery,
    CoreStageSubstatusCode,
    HistoricalLifecycleFacet,
    query_core_stage_page,
)
from subsystems.orders.core_stage_projection_query import (
    CoreStageBranchType,
    CoreStageCode,
    CoreStageProjectionContractError,
)
from subsystems.orders.government_subsidy_projection_query import (
    GovernmentSubsidyProjectionContractError,
    GovernmentSubsidyProjectionQuery,
    GovernmentSubsidySubstatusCode,
    query_government_subsidy_projection_page,
)
from subsystems.orders.historical_adoption_evidence_query import (
    HistoricalOrderAdoptionEvidenceNotFound,
    query_historical_order_adoption_evidence,
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
        422: {"model": GlobalTypedErrorResponseView, "description": "查詢條件不符合公開契約"},
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
    historical_lifecycle: Annotated[HistoricalLifecycleFacet | None, Query()] = None,
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
                historical_lifecycle=historical_lifecycle,
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


@router.get(
    "/government-subsidy-projections",
    response_model=BaseResponse[OrderGovernmentSubsidyProjectionPageView],
    responses={
        304: {"description": "Government Subsidy side-lane projection 自上次查詢後未變更"},
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
    case_no_search: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    substatus_code: Annotated[GovernmentSubsidySubstatusCode | None, Query()] = None,
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
        CoreStageProjectionContractError,
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
    "/{case_no}/historical-adoption-evidence",
    response_model=BaseResponse[HistoricalOrderAdoptionEvidenceView],
    responses={
        401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證"},
        403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權查詢歷史 adoption evidence"},
        404: {"model": GlobalTypedErrorResponseView, "description": "案件沒有 adopted historical evidence"},
        409: {"model": GlobalTypedErrorResponseView, "description": "已保存的 historical evidence 契約不一致"},
        500: {"model": GlobalTypedErrorResponseView, "description": "historical evidence 查詢失敗"},
        503: {"model": GlobalTypedErrorResponseView, "description": "historical evidence 暫時無法使用"},
    },
)
def get_historical_order_adoption_evidence(
    case_no: str = Path(..., min_length=1, max_length=50, pattern=r"^[^\s]+$"),
    principal: AdminPrincipal = Depends(require_system_admin),
    repository=Depends(get_historical_order_adoption_evidence_repository),
):
    del principal
    try:
        evidence = query_historical_order_adoption_evidence(repository, case_no)
        view = HistoricalOrderAdoptionEvidenceView.model_validate(evidence, from_attributes=True)
    except HistoricalOrderAdoptionEvidenceNotFound as error:
        raise typed_http_error(
            404,
            "not_found",
            "historical_order_adoption_evidence_not_found",
            "找不到此案件已採納的歷史來源證據。",
            "historical-order-adoption-evidence-query",
        ) from error
    except ValueError as error:
        raise typed_http_error(
            409,
            "conflict",
            "historical_order_adoption_evidence_invalid",
            "已保存的歷史來源證據無法產生一致的唯讀投影。",
            "historical-order-adoption-evidence-query",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        raise typed_http_error(
            503,
            "unavailable",
            "historical_order_adoption_evidence_unavailable",
            "歷史來源證據目前無法讀取。",
            "historical-order-adoption-evidence-query",
            retryable=True,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "historical_order_adoption_evidence_internal_error",
            "歷史來源證據查詢失敗。",
            "historical-order-adoption-evidence-query",
        ) from error
    return BaseResponse(data=view, message="成功取得歷史訂單 adoption evidence")


__all__ = ["router"]

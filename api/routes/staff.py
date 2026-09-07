"""
File: staff.py
Description: 提供管理員會話保護的 bounded Staff 摘要 cursor 查詢與退役全量入口。
"""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_case_preference_summary import (
    get_staff_case_preference_summary_application,
)
from api.dependencies.staff_summary import get_staff_summary_application
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.staff_case_preference_summary import StaffCasePreferenceSummaryView
from api.schemas.staff_summary import StaffSummaryPageView, StaffSummaryView
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.case_preference_summary_query import (
    StaffCasePreferenceSummaryContractError,
    StaffCasePreferenceSummaryQueryApplication,
)
from subsystems.staff.summary_query import (
    StaffSummaryContractError,
    StaffSummaryQueryApplication,
    StaffSummaryQueryRequest,
)

router = APIRouter(prefix="/api/v1/staff", tags=["Staff 服務人員/月嫂名冊"])


@router.get("/summaries", response_model=BaseResponse[StaffSummaryPageView])
def get_staff_summaries(
    page_size: int = Query(default=200, ge=1, le=200),
    after_id: int | None = Query(default=None, ge=1),
    staff_id: int | None = Query(default=None, ge=1),
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffSummaryQueryApplication = Depends(get_staff_summary_application),
) -> BaseResponse[StaffSummaryPageView]:
    """Return a bounded staff selector page without exposing the staff master."""
    del principal
    correlation = correlation_id or uuid4().hex
    if staff_id is not None and after_id is not None:
        raise typed_http_error(
            422,
            "validation",
            "staff_summary_query_params_conflict",
            "staff_id 與 after_id 不得同時提供。",
            correlation,
        )
    try:
        page = application.query(
            StaffSummaryQueryRequest(
                page_size=page_size,
                after_id=after_id,
                staff_id=staff_id,
            )
        )
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error(
            "staff_summary_query_internal_error",
            "服務人員摘要查詢失敗。",
            correlation,
        ) from error
    except StaffSummaryContractError as error:
        raise internal_query_error(
            "staff_summary_projection_invalid",
            "服務人員摘要投影契約無效。",
            correlation,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "staff_summary_query_internal_error",
            "服務人員摘要查詢失敗。",
            correlation,
        ) from error
    return BaseResponse(
        data=StaffSummaryPageView(
            items=[
                StaffSummaryView.model_validate(item, from_attributes=True)
                for item in page.items
            ],
            next_cursor=page.next_cursor,
        ),
        message="成功取得服務人員摘要",
    )


@router.get(
    "/{staff_id}/case-preference-summary",
    response_model=BaseResponse[StaffCasePreferenceSummaryView],
)
def get_staff_case_preference_summary(
    staff_id: int = Path(..., ge=1),
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffCasePreferenceSummaryQueryApplication = Depends(
        get_staff_case_preference_summary_application
    ),
) -> BaseResponse[StaffCasePreferenceSummaryView]:
    """Return one bounded Staff case-preference projection for roster consumers."""
    del principal
    correlation = correlation_id or uuid4().hex
    try:
        summary = application.get(staff_id)
    except (OperationalError, ProgrammingError) as error:
        raise internal_query_error(
            "staff_case_preference_summary_query_internal_error",
            "服務人員案件偏好摘要查詢失敗。",
            correlation,
        ) from error
    except StaffCasePreferenceSummaryContractError as error:
        raise internal_query_error(
            "staff_case_preference_summary_projection_invalid",
            "服務人員案件偏好摘要投影契約無效。",
            correlation,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "staff_case_preference_summary_query_internal_error",
            "服務人員案件偏好摘要查詢失敗。",
            correlation,
        ) from error

    if summary is None:
        raise typed_http_error(
            404,
            "not_found",
            "staff_not_found",
            "查無服務人員。",
            correlation,
        )

    return BaseResponse(
        data=StaffCasePreferenceSummaryView.from_summary(summary),
        message="成功取得服務人員案件偏好摘要",
    )


@router.get("", include_in_schema=False)
def get_all_staff() -> None:
    """Reject the retired unbounded staff directory endpoint."""
    raise HTTPException(
        status_code=410,
        detail="全量服務人員名冊已退役，請使用 /summaries cursor 分頁查詢。",
    )

"""
File: staff.py
Description: 提供管理員會話保護的 bounded Staff 摘要 cursor 查詢與退役全量入口。
"""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.dependencies.admin_auth import require_admin
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.staff_summary import StaffSummaryPageView, StaffSummaryView
from infrastructure.mysql import mysql_adapter as db_service
from subsystems.access.authentication_session import AdminPrincipal

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
        connection = db_service.get_connection()
        with connection.cursor() as cursor:
            if staff_id is not None:
                cursor.execute(
                    "SELECT id, name, phone FROM staff WHERE id=%s LIMIT 1",
                    (staff_id,),
                )
            else:
                cursor.execute(
                    "SELECT id, name, phone FROM staff "
                    "WHERE id > %s ORDER BY id LIMIT %s",
                    (after_id or 0, page_size + 1),
                )
            rows = cursor.fetchall()
    except Exception as error:
        raise internal_query_error(
            "staff_summary_query_internal_error",
            "服務人員摘要查詢失敗。",
            correlation,
        ) from error
    finally:
        if "connection" in locals():
            connection.close()
    has_next_page = staff_id is None and len(rows) > page_size
    page_rows = rows[:page_size]
    next_cursor = int(page_rows[-1]["id"]) if has_next_page else None
    return BaseResponse(
        data=StaffSummaryPageView(
            items=[StaffSummaryView.model_validate(row) for row in page_rows],
            next_cursor=next_cursor,
        ),
        message="成功取得服務人員摘要",
    )


@router.get("", include_in_schema=False)
def get_all_staff() -> None:
    """Reject the retired unbounded staff directory endpoint."""
    raise HTTPException(
        status_code=410,
        detail="全量服務人員名冊已退役，請使用 /summaries cursor 分頁查詢。",
    )

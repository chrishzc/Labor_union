from fastapi import APIRouter, HTTPException, Path, Query
from typing import List, Dict, Any
from infrastructure.mysql import mysql_adapter as db_service
from api.error_contracts import internal_query_error
from api.schemas.base import BaseResponse
from api.schemas.staff_summary import StaffSummaryPageView, StaffSummaryView

router = APIRouter(prefix="/api/v1/staff", tags=["Staff 服務人員/月嫂名冊"])


@router.get("/summaries", response_model=BaseResponse[StaffSummaryPageView])
def get_staff_summaries(
    page_size: int = Query(default=200, ge=1, le=200),
    after_id: int | None = Query(default=None, ge=1),
) -> BaseResponse[StaffSummaryPageView]:
    """Return a bounded staff selector page without exposing the staff master."""
    try:
        connection = db_service.get_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, phone FROM staff WHERE id > %s ORDER BY id LIMIT %s",
                (after_id or 0, page_size + 1),
            )
            rows = cursor.fetchall()
    except Exception as error:
        raise internal_query_error(
            "staff_summary_query_internal_error",
            "服務人員摘要查詢失敗。",
            "staff-summary-query",
        ) from error
    finally:
        if "connection" in locals():
            connection.close()
    has_next_page = len(rows) > page_size
    page_rows = rows[:page_size]
    next_cursor = int(page_rows[-1]["id"]) if has_next_page else None
    return BaseResponse(
        data=StaffSummaryPageView(
            items=[StaffSummaryView.model_validate(row) for row in page_rows],
            next_cursor=next_cursor,
        ),
        message="成功取得服務人員摘要",
    )

@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_staff():
    """取得全量服務人員/月嫂名冊資料表"""
    try:
        data = db_service.get_table_data("staff")
        return BaseResponse(data=data, message="成功取得服務人員列表")
    except Exception as error:
        raise internal_query_error(
            "staff_query_internal_error",
            "服務人員名冊查詢失敗。",
            "staff-query",
        ) from error

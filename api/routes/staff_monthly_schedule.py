"""
================================================================================
檔案名稱: api/routes/staff_monthly_schedule.py
功能說明: 月嫂月度檔期視圖 API 路由 (StaffMonthlyCalendarScheduleRouter)
================================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from api.dependencies.admin_auth import require_system_admin
from api.schemas.base import BaseResponse
from api.schemas.staff_monthly_schedule import StaffMonthlyScheduleView
from api.error_contracts import internal_query_error
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling import staff_monthly_calendar_query
from infrastructure.mysql.mysql_adapter import get_connection


staff_monthly_calendar_query.get_connection = get_connection

router = APIRouter(prefix="/api/v1/staff", tags=["Staff 服務人員月度檔期排班"])


def _http_status_for_service_error(error_message: str) -> int:
    if "不存在" in error_message:
        return 404
    return 422


@router.get(
    "/{staff_id}/monthly-schedule",
    response_model=BaseResponse[StaffMonthlyScheduleView],
    response_model_exclude_none=True,
)
def get_staff_monthly_schedule(
    staff_id: int = Path(..., description="服務人員 ID"),
    year: int = Query(..., description="年份", ge=1900, le=2100),
    month: int = Query(..., description="月份", ge=1, le=12),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """取得月嫂月度檔期排班視圖 (含 days: [] 陣列與 schedule_map)"""
    del principal
    try:
        data = staff_monthly_calendar_query.get_staff_monthly_calendar_schedule(
            staff_id=staff_id,
            year=year,
            month=month,
        )
        return BaseResponse(
            data=StaffMonthlyScheduleView.model_validate(data),
            message="成功取得月嫂月度檔期排班視圖",
        )
    except ValueError as exc:
        raise HTTPException(status_code=_http_status_for_service_error(str(exc)), detail=str(exc))
    except Exception as error:
        raise internal_query_error(
            "staff_monthly_schedule_internal_error",
            "月嫂月度檔期查詢失敗。",
            "staff-monthly-schedule-query",
        ) from error

"""
File: order_schedule_calculation.py
Description: 接收 typed 出勤精算條件並轉交 Scheduling subsystem，不在 route 重算日期。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from api.dependencies.admin_auth import require_system_admin
from api.schemas.base import BaseResponse
from api.schemas.orders import ScheduleCalculationRequest
from api.schemas.schedule_precision import SchedulePrecisionResultView
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling import attendance_schedule_query
from infrastructure.mysql.mysql_adapter import calculate_attendance_schedule


attendance_schedule_query.calculate_attendance_schedule = calculate_attendance_schedule

router = APIRouter(prefix="/api/v1/orders", tags=["Orders 訂單與排班精算"])

@router.post(
    "/calculate-schedule",
    response_model=BaseResponse[SchedulePrecisionResultView],
)
def calculate_schedule(
    req: ScheduleCalculationRequest,
    principal: AdminPrincipal = Depends(require_system_admin),
) -> BaseResponse[SchedulePrecisionResultView]:
    """精算服務人員出勤日、扣除排休與國定假日順延完工日"""
    del principal
    try:
        res = attendance_schedule_query.calculate_order_attendance_schedule(
            actual_start_date=req.actual_start_date,
            target_service_days=req.target_service_days,
            service_mode=req.service_mode,
            custom_holiday_rest_dates=req.custom_holiday_rest_dates,
            custom_leave_dates=req.custom_leave_dates,
            custom_work_dates=req.custom_work_dates,
            custom_rest_weekdays=req.custom_rest_weekdays,
            monthly_salary_base=req.monthly_salary_base,
        )
        return BaseResponse(
            data=SchedulePrecisionResultView.model_validate(res),
            message="成功完成排班與順延完工日試算",
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "schedule_precision_projection_invalid"},
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={"code": "schedule_precision_unavailable"},
        ) from error

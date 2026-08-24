"""
File: order_schedule_calculation.py
Description: 接收 typed 出勤精算條件並轉交 Scheduling subsystem，不在 route 重算日期。
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from api.schemas.base import BaseResponse
from api.schemas.orders import ScheduleCalculationRequest
from subsystems.scheduling import attendance_schedule_query

router = APIRouter(prefix="/api/v1/orders", tags=["Orders 訂單與排班精算"])

@router.post("/calculate-schedule", response_model=BaseResponse[Dict[str, Any]])
def calculate_schedule(req: ScheduleCalculationRequest):
    """精算服務人員出勤日、扣除排休與國定假日順延完工日"""
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
        return BaseResponse(data=res, message="成功完成排班與順延完工日試算")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

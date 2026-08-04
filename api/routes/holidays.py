from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Dict, Any
from datetime import date
from api.dependencies.admin_auth import require_system_admin
from api.error_contracts import internal_query_error
from infrastructure.mysql import mysql_adapter as db_service
from subsystems.scheduling.holiday_query_cache import (
    invalidate_holiday_query_cache,
    query_holidays,
)
from subsystems.access.authentication_session import AdminPrincipal
from api.schemas.base import BaseResponse
from api.schemas.holidays import HolidayCreateRequest

router = APIRouter(prefix="/api/v1/holidays", tags=["Holidays 國定假日設定"])

@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_holidays(
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """取得中華民國國定假日設定列表"""
    try:
        data = query_holidays()
        return BaseResponse(data=data, message="成功取得國定假日列表")
    except Exception as error:
        raise internal_query_error(
            "holiday_query_internal_error",
            "國定假日查詢失敗。",
            "holiday-query",
        ) from error

@router.post("", response_model=BaseResponse[bool])
def add_or_update_holiday(
    req: HolidayCreateRequest,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """新增或更新國定假日"""
    try:
        success = db_service.add_or_update_holiday(
            holiday_date=req.holiday_date,
            holiday_name=req.holiday_name,
            is_double_pay_default=req.is_double_pay_default
        )
        invalidate_holiday_query_cache()
        return BaseResponse(data=success, message="成功儲存國定假日")
    except Exception as error:
        raise internal_query_error(
            "holiday_save_internal_error",
            "國定假日儲存失敗。",
            "holiday-save",
        ) from error

@router.delete("/{holiday_date}", response_model=BaseResponse[bool])
def delete_holiday(
    holiday_date: date = Path(..., description="假日日期 (YYYY-MM-DD)"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """刪除指定國定假日"""
    try:
        success = db_service.delete_holiday(holiday_date)
        invalidate_holiday_query_cache()
        return BaseResponse(data=success, message="成功刪除國定假日")
    except Exception as error:
        raise internal_query_error(
            "holiday_delete_internal_error",
            "國定假日刪除失敗。",
            "holiday-delete",
        ) from error

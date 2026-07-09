from fastapi import APIRouter, HTTPException, Path
from typing import List, Dict, Any
from services import db_service
from api.schemas.base import BaseResponse
from api.schemas.orders import (
    OrderFullUpdateRequest, 
    OrderStatusUpdateRequest, 
    ScheduleCalculationRequest
)

router = APIRouter(prefix="/api/v1/orders", tags=["Orders 訂單管理"])

@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_orders():
    """取得全量訂單 36 欄位計算視圖資料清單"""
    try:
        data = db_service.get_order_details()
        return BaseResponse(data=data, message="成功取得全量訂單列表")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{order_id}", response_model=BaseResponse[Dict[str, Any]])
def get_order_by_id(order_id: int = Path(..., description="訂單 ID")):
    """依訂單 ID 取得單筆訂單詳細資訊"""
    try:
        all_orders = db_service.get_order_details()
        order = next((o for o in all_orders if o['order_id'] == order_id), None)
        if not order:
            raise HTTPException(status_code=404, detail=f"找不到 ID 為 {order_id} 的訂單")
        return BaseResponse(data=order, message="成功取得單筆訂單資訊")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{order_id}/full-details", response_model=BaseResponse[bool])
def update_order_full_details(
    req: OrderFullUpdateRequest,
    order_id: int = Path(..., description="訂單 ID")
):
    """更新單筆訂單 36 欄位主要資料 (天數、時數、資格、樓層費、起訖日與客戶姓名)"""
    try:
        update_dict = req.model_dump()
        success = db_service.update_order_full_details(order_id, update_dict)
        return BaseResponse(data=success, message="成功更新訂單 36 欄位資料")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{order_id}/status", response_model=BaseResponse[bool])
def update_order_status(
    req: OrderStatusUpdateRequest,
    order_id: int = Path(..., description="訂單 ID")
):
    """更新訂單成立狀態與取消原因"""
    try:
        success = db_service.update_order_status(order_id, req.status, req.cancel_reason)
        return BaseResponse(data=success, message="成功更新訂單狀態")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calculate-schedule", response_model=BaseResponse[Dict[str, Any]])
def calculate_schedule(req: ScheduleCalculationRequest):
    """精算服務人員出勤日、扣除排休與國定假日順延完工日"""
    try:
        res = db_service.calculate_attendance_schedule(
            actual_start_date=req.actual_start_date,
            target_service_days=req.target_service_days,
            service_mode=req.service_mode,
            custom_holiday_rest_dates=req.custom_holiday_rest_dates
        )
        return BaseResponse(data=res, message="成功完成排班與順延完工日試算")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

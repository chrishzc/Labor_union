from fastapi import APIRouter, HTTPException, Path
from typing import List, Dict, Any
from services import db_service
from api.schemas.base import BaseResponse
from api.schemas.payments import PaymentUpdateRequest

router = APIRouter(prefix="/api/v1/payments", tags=["Payments 財務對帳"])

@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_payments():
    """取得所有財務實收與對帳資料"""
    try:
        data = db_service.get_table_data("payments")
        return BaseResponse(data=data, message="成功取得財務對帳列表")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{order_id}", response_model=BaseResponse[bool])
def update_payment(
    req: PaymentUpdateRequest,
    order_id: int = Path(..., description="訂單 ID")
):
    """更新特定訂單之實收訂金、尾款、月嫂費用與帳務備註"""
    try:
        success = db_service.update_payment_details(
            order_id=order_id,
            amount_receivable=req.amount_receivable,
            deposit_received=req.deposit_received,
            balance_received=req.balance_received,
            caregiver_fee=req.caregiver_fee,
            payment_status=req.payment_status,
            notes=req.notes,
            deposit_received_at=req.deposit_received_at,
            balance_received_at=req.balance_received_at,
            caregiver_paid_at=req.caregiver_paid_at
        )
        return BaseResponse(data=success, message="成功更新實收帳務資訊")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

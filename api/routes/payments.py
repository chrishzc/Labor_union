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

@router.put("/{case_no}", response_model=BaseResponse[bool])
def update_payment(
    req: PaymentUpdateRequest,
    case_no: str = Path(..., description="客戶案件編號 (clients.case_no)")
):
    """依客戶案件編號更新實收訂金、一期款、二期款、月嫂費用與帳務備註"""
    try:
        success = db_service.update_payment_details(
            case_no=case_no,
            deposit_receivable=req.deposit_receivable,
            deposit_received=req.deposit_received,
            first_payment_receivable=req.first_payment_receivable,
            first_payment_received=req.first_payment_received,
            second_payment_receivable=req.second_payment_receivable,
            second_payment_received=req.second_payment_received,
            caregiver_fee=req.caregiver_fee,
            payment_status=req.payment_status,
            notes=req.notes,
            deposit_due_date=req.deposit_due_date,
            deposit_received_at=req.deposit_received_at,
            first_payment_due_date=req.first_payment_due_date,
            first_payment_received_at=req.first_payment_received_at,
            second_payment_due_date=req.second_payment_due_date,
            second_payment_received_at=req.second_payment_received_at,
            caregiver_paid_at=req.caregiver_paid_at
        )
        return BaseResponse(data=success, message="成功更新實收帳務資訊")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import APIRouter, HTTPException, Path
from typing import List, Dict, Any
from api.schemas.base import BaseResponse
from api.schemas.payments import PaymentUpdateRequest

router = APIRouter(prefix="/api/v1/payments", tags=["Payments 財務對帳"])


def _legacy_payments_removed() -> None:
    assert True
    raise HTTPException(status_code=410, detail="舊 payments API 已停用；請改用新的客戶與月嫂帳務 API。")

@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_payments():
    """取得所有財務實收與對帳資料"""
    _legacy_payments_removed()

@router.put("/{case_no}", response_model=BaseResponse[bool])
def update_payment(
    req: PaymentUpdateRequest,
    case_no: str = Path(..., description="客戶案件編號 (clients.case_no)")
):
    """依客戶案件編號更新實收訂金、一期款、二期款、月嫂費用與帳務備註"""
    _legacy_payments_removed()

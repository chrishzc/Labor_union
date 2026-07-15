from fastapi import APIRouter, HTTPException, Path
from typing import List, Dict, Any, Optional
from datetime import date
from pydantic import BaseModel, Field, model_validator
from api.schemas.base import BaseResponse
from services.db_service import get_connection
from services.staff_payment_transactions import record_staff_payment_transaction

router = APIRouter(prefix="/api/v1/staff-payments", tags=["Staff Payments 月嫂帳務"])


class StaffTransactionCreate(BaseModel):
    @model_validator(mode="after")
    def require_non_blank_notes(self):
        if not self.notes or not self.notes.strip():
            raise ValueError("Manual payment reason must not be blank")
        self.notes = self.notes.strip()
        return self

    staff_payment_id: int = Field(..., description="月嫂付款單 ID")
    transaction_type: str = Field("transfer", description="交易類型 (transfer, return, reversal)")
    transaction_status: str = Field("succeeded", description="交易狀態 (succeeded, failed, reversed)")
    amount: float = Field(..., description="交易金額")
    occurred_at: date = Field(..., description="交易日期")
    external_reference: str = Field(..., description="外部轉帳流水號")
    notes: Optional[str] = Field(None, description="備註")


@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_staff_payments():
    """取得所有月嫂應付帳務列表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM staff_payments ORDER BY id DESC")
            data = cursor.fetchall()
            return BaseResponse(data=data, message="成功取得所有月嫂應付帳務")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{case_no}", response_model=BaseResponse[List[Dict[str, Any]]])
def get_staff_payments_by_case_no(case_no: str = Path(..., description="案件編號")):
    """依案件編號取得該案之月嫂帳務與交易明細"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM staff_payments WHERE case_no = %s", (case_no,))
            payments = cursor.fetchall()
            if not payments:
                return BaseResponse(data=[], message="此案件無任何月嫂應付帳務")
            
            # 針對每一筆付款單讀取其交易明細
            result = []
            for payment in payments:
                pay_dict = dict(payment)
                cursor.execute("SELECT * FROM staff_payment_transactions WHERE staff_payment_id = %s ORDER BY occurred_at ASC, id ASC", (payment["id"],))
                pay_dict["transactions"] = cursor.fetchall()
                result.append(pay_dict)
                
            return BaseResponse(data=result, message="成功取得案件月嫂帳務與明細")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/transaction", response_model=BaseResponse[Dict[str, Any]])
def create_staff_transaction(req: StaffTransactionCreate):
    """新增月嫂付款交易明細並自動更新狀態"""
    try:
        # 呼叫服務層持久化與計算
        update_result = record_staff_payment_transaction(
            staff_payment_id=req.staff_payment_id,
            transaction_type=req.transaction_type,
            transaction_status=req.transaction_status,
            amount=req.amount,
            occurred_at=req.occurred_at.strftime("%Y-%m-%d"),
            external_reference=req.external_reference,
            notes=req.notes
        )
        return BaseResponse(data=update_result, message="月嫂轉帳交易紀錄新增並計算完成")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

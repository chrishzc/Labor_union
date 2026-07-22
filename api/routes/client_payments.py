from fastapi import APIRouter, HTTPException, Path
from typing import List, Dict, Any, Literal, Optional
from datetime import date
from pydantic import BaseModel, Field, field_validator
from api.schemas.base import BaseResponse
from services.db_service import get_connection
from services.db_service import backfill_client_payment_due_dates as run_backfill_client_payment_due_dates
from services.client_payment_writer import record_client_payment_transaction

router = APIRouter(prefix="/api/v1/client-payments", tags=["Client Payments 客戶帳務"])


class ClientTransactionCreate(BaseModel):
    case_no: str = Field(..., description="案件編號")
    stage: Literal["deposit", "first_payment", "second_payment"] = Field(..., description="收款階段")
    transaction_type: Literal["receipt", "reversal"] = Field("receipt", description="交易類型")
    transaction_status: Literal["succeeded", "failed", "reversed"] = Field("succeeded", description="交易狀態")
    amount: float = Field(..., gt=0, description="交易金額")
    occurred_at: date = Field(..., description="交易日期")
    external_reference: str = Field(..., description="外部流水號")
    # Summary columns are derived from transaction records and cannot be edited here.
    notes: str = Field(..., min_length=1, description="人工補登或更正原因")

    @field_validator("notes")
    @classmethod
    def notes_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("人工補登交易必須填寫原因")
        return value


@router.get("", response_model=BaseResponse[List[Dict[str, Any]]])
def get_all_client_payments():
    """取得所有客戶帳務摘要列表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM client_payments ORDER BY id DESC")
            data = cursor.fetchall()
            return BaseResponse(data=data, message="成功取得所有客戶帳務摘要")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{case_no}", response_model=BaseResponse[Dict[str, Any]])
def get_client_payment_by_case_no(case_no: str = Path(..., description="案件編號")):
    """依案件編號取得單筆客戶帳務摘要與交易明細"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM client_payments WHERE case_no = %s", (case_no,))
            payment = cursor.fetchone()
            if not payment:
                raise HTTPException(status_code=404, detail="找不到該案件的客戶帳務摘要")
            
            cursor.execute("SELECT * FROM client_payment_transactions WHERE client_payment_id = %s ORDER BY occurred_at ASC, id ASC", (payment["id"],))
            transactions = cursor.fetchall()
            
            result = dict(payment)
            result["transactions"] = transactions
            return BaseResponse(data=result, message="成功取得客戶帳務與明細")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/due-dates/backfill", response_model=BaseResponse[Dict[str, Any]])
def backfill_client_payment_due_dates(case_no: Optional[str] = None):
    """回補 client_payments 的應收日期欄位（從 v_order_details 補齊空值）。"""
    try:
        result = run_backfill_client_payment_due_dates(case_no=case_no)
        return BaseResponse(
            data=result,
            message="客戶帳務應收日期回補完成",
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transaction", response_model=BaseResponse[Dict[str, Any]])
def create_client_transaction(req: ClientTransactionCreate):
    """新增客戶交易明細並自動重新計算更新摘要表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM client_payments WHERE case_no = %s FOR UPDATE", (req.case_no,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="找不到對應的客戶帳務主表記錄")
            client_payment_id = row["id"]
    finally:
        conn.close()

    try:
        # 呼叫服務層持久化與計算
        update_result = record_client_payment_transaction(
            client_payment_id=client_payment_id,
            stage=req.stage,
            transaction_type=req.transaction_type,
            transaction_status=req.transaction_status,
            amount=req.amount,
            occurred_at=req.occurred_at.strftime("%Y-%m-%d"),
            external_reference=req.external_reference,
            notes=req.notes
        )
        return BaseResponse(data=update_result, message="客戶交易紀錄新增並計算完成")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

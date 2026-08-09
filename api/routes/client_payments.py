from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Dict, Any, Literal, Optional
from datetime import date
from pydantic import BaseModel, Field, field_validator, model_validator
from api.schemas.base import BaseResponse
from api.dependencies.admin_auth import require_system_admin
from subsystems.access.authentication_session import AdminPrincipal
from infrastructure.mysql.mysql_adapter import get_connection

router = APIRouter(prefix="/api/v1/client-payments", tags=["Client Payments 客戶帳務"])


class ClientTransactionCreate(BaseModel):
    case_no: str = Field(..., description="案件編號")
    stage: Literal["deposit", "first_payment", "second_payment"] = Field(..., description="收款階段")
    transaction_type: Literal["receipt", "reversal"] = Field("receipt", description="交易類型")
    transaction_status: Literal["succeeded"] = Field(
        "succeeded",
        description="正式帳務只接受成功交易；失敗嘗試不寫入 canonical ledger",
    )
    amount: float = Field(..., gt=0, description="交易金額")
    occurred_at: date = Field(..., description="交易日期")
    external_reference: str = Field(..., description="外部流水號")
    reversal_of_transaction_id: int | None = Field(
        None,
        gt=0,
        strict=True,
        description="沖銷交易所對應的原始收款交易 ID",
    )
    lifecycle_expected_version: int | None = Field(
        None,
        ge=0,
        strict=True,
        description="訂金事件使用的訂單 lifecycle optimistic version",
    )
    # Summary columns are derived from transaction records and cannot be edited here.
    notes: str = Field(..., min_length=1, description="人工補登或更正原因")

    @field_validator("notes")
    @classmethod
    def notes_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("人工補登交易必須填寫原因")
        return value

    @model_validator(mode="after")
    def validate_reversal_link(self):
        if self.transaction_type == "receipt" and self.reversal_of_transaction_id is not None:
            raise ValueError("收款交易不可指定 reversal_of_transaction_id")
        if self.transaction_type == "reversal" and self.reversal_of_transaction_id is None:
            raise ValueError("沖銷交易必須指定 reversal_of_transaction_id")
        if self.stage == "deposit" and self.lifecycle_expected_version is None:
            raise ValueError("訂金交易必須提供 lifecycle_expected_version")
        if self.stage != "deposit" and self.lifecycle_expected_version is not None:
            raise ValueError("第一期／第二期交易不可提供 lifecycle_expected_version")
        return self


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
def backfill_client_payment_due_dates(
    case_no: Optional[str] = None,
    _: AdminPrincipal = Depends(require_system_admin),
):
    """Legacy mutable projection backfill is no longer a production command."""
    del case_no
    raise HTTPException(
        status_code=410,
        detail="legacy_client_payment_backfill_removed",
    )


@router.post("/transaction", response_model=BaseResponse[Dict[str, Any]])
def create_client_transaction(
    req: ClientTransactionCreate,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Legacy free-form transaction writer is permanently unavailable."""
    del req, principal
    raise HTTPException(
        status_code=410,
        detail="use_client_finance_preview_apply",
    )

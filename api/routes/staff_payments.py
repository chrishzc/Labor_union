from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field, model_validator
from api.schemas.base import BaseResponse
from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_payments import get_staff_payment_query_application
from api.schemas.staff_payments import StaffPaymentSummaryView
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff_payables.legacy_payment_query import StaffPaymentQueryApplication

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


@router.get("", response_model=BaseResponse[List[StaffPaymentSummaryView]])
def get_all_staff_payments(
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffPaymentQueryApplication = Depends(
        get_staff_payment_query_application
    ),
):
    """取得 bounded typed Staff Payables compatibility projection."""
    del principal
    try:
        return BaseResponse(
            data=list(application.query_all()), message="成功取得所有月嫂應付帳務"
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail="staff_payments_query_failed") from error


@router.get("/{case_no}", response_model=BaseResponse[List[StaffPaymentSummaryView]])
def get_staff_payments_by_case_no(
    case_no: str = Path(..., min_length=1, max_length=50, description="案件編號"),
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffPaymentQueryApplication = Depends(
        get_staff_payment_query_application
    ),
):
    """依案件編號取得該案之月嫂帳務與交易明細"""
    del principal
    try:
        data = list(application.query_by_case_no(case_no))
        message = "成功取得案件月嫂帳務與明細" if data else "此案件無任何月嫂應付帳務"
        return BaseResponse(data=data, message=message)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid_case_number") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="staff_payments_query_failed") from error


@router.post("/transaction", response_model=BaseResponse[None])
def create_staff_transaction(
    req: StaffTransactionCreate,
    principal: AdminPrincipal = Depends(require_admin),
):
    """Legacy free-form staff transaction writer is permanently unavailable."""
    del req, principal
    raise HTTPException(
        status_code=410,
        detail="use_staff_payables_preview_apply",
    )

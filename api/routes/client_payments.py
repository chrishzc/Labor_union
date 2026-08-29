from fastapi import APIRouter, Depends, HTTPException, Path
from typing import Literal, Optional
from datetime import date
from pydantic import BaseModel, Field, field_validator, model_validator
from api.dependencies.client_payments import (
    get_client_finance_query_application,
)
from api.schemas.base import BaseResponse
from api.schemas.client_payments import (
    ClientFinanceAllocationView,
    ClientFinanceCaseView,
    ClientFinanceLedgerEntryView,
    ClientFinanceObligationView,
    ClientFinancePageView,
    ClientFinanceCaseSummaryView,
)
from api.dependencies.admin_auth import require_admin, require_system_admin
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.client_payments_query import (
    ClientFinanceQueryApplication,
)
from infrastructure.mysql.client_payments_query_repository import (
    ClientFinanceCaseNotFound,
)

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


@router.get("", response_model=BaseResponse[ClientFinancePageView])
def get_all_client_payments(
    principal: AdminPrincipal = Depends(require_admin),
    application: ClientFinanceQueryApplication = Depends(
        get_client_finance_query_application
    ),
):
    """取得 bounded Client Finance 案件摘要；不暴露 compatibility table rows。"""
    del principal
    try:
        result = application.query_all()
        return BaseResponse(
            data=ClientFinancePageView(
                cases=[
                    ClientFinanceCaseSummaryView(
                        case_no=item.case_no,
                        account_version=item.account_version,
                        open_receivable_amount_ntd=item.open_receivable_amount_ntd,
                        open_payable_amount_ntd=item.open_payable_amount_ntd,
                        obligation_count=item.obligation_count,
                        ledger_entry_count=item.ledger_entry_count,
                    )
                    for item in result.cases
                ]
            ),
            message="成功取得 Client Finance 案件摘要",
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail="client_finance_query_failed") from error


@router.get("/{case_no}", response_model=BaseResponse[ClientFinanceCaseView])
def get_client_payment_by_case_no(
    case_no: str = Path(..., min_length=1, max_length=50, description="案件編號"),
    principal: AdminPrincipal = Depends(require_admin),
    application: ClientFinanceQueryApplication = Depends(
        get_client_finance_query_application
    ),
):
    """依案件編號取得 bounded Client Finance roots 與 immutable ledger。"""
    del principal
    try:
        result = application.query_case(case_no)
        return BaseResponse(
            data=ClientFinanceCaseView(
                case_no=result.case_no,
                account_version=result.account_version,
                obligations=[
                    ClientFinanceObligationView(
                        obligation_identity=item.obligation_identity,
                        obligation_type=item.obligation_type,
                        direction=item.direction,
                        amount_due_ntd=item.amount_due_ntd,
                        due_date=item.due_date,
                        status=item.status,
                        projection_version=item.projection_version,
                    )
                    for item in result.obligations
                ],
                ledger_entries=[
                    ClientFinanceLedgerEntryView(
                        entry_id=item.entry_id,
                        entry_type=item.entry_type,
                        amount_ntd=item.amount_ntd,
                        occurred_on=item.occurred_on,
                        reconciliation_reference=item.reconciliation_reference,
                        reversal_of_entry_id=item.reversal_of_entry_id,
                        created_at=item.created_at,
                        allocations=[
                            ClientFinanceAllocationView(
                                obligation_identity=allocation.obligation_identity,
                                amount_ntd=allocation.amount_ntd,
                            )
                            for allocation in item.allocations
                        ],
                    )
                    for item in result.ledger_entries
                ],
            ),
            message="成功取得 Client Finance 案件根事實",
        )
    except ClientFinanceCaseNotFound as error:
        raise HTTPException(
            status_code=404, detail="client_finance_case_not_found"
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail="client_finance_query_invalid") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="client_finance_query_failed") from error


@router.post("/due-dates/backfill")
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


@router.post("/transaction")
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

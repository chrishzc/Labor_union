from fastapi import APIRouter, Depends, Header, HTTPException, Path
from typing import Annotated, Literal, Optional
from datetime import date
from pydantic import BaseModel, Field, field_validator, model_validator
from api.dependencies.client_payments import (
    get_client_finance_query_application,
    get_historical_client_payment_workflow,
)
from api.schemas.base import BaseResponse
from api.schemas.client_payments import (
    ClientFinanceAllocationView,
    ClientFinanceCaseView,
    ClientFinanceLedgerEntryView,
    ClientFinanceObligationView,
    ClientFinancePageView,
    ClientFinanceCaseSummaryView,
    HistoricalClientObligationView,
    HistoricalClientPaymentApplyBody,
    HistoricalClientPaymentIntentBody,
    HistoricalClientPaymentPreviewView,
    HistoricalClientPaymentProjectionView,
    HistoricalClientPaymentQueryView,
    HistoricalClientPaymentReadbackView,
    HistoricalClientPaymentReceiptView,
)
from api.dependencies.admin_auth import require_admin, require_system_admin
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.client_payments_query import (
    ClientFinanceQueryApplication,
)
from infrastructure.mysql.client_payments_query_repository import (
    ClientFinanceCaseNotFound,
)
from domains.client_finance.historical_payment import (
    HistoricalClientConfirmationKind,
    HistoricalClientDirection,
    HistoricalClientPaymentIntent,
    HistoricalClientSourceAvailability,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.historical_payment_settlement import (
    ApplyHistoricalClientPayment,
    HistoricalClientPaymentError,
    HistoricalClientPaymentWorkflow,
)

router = APIRouter(prefix="/api/v1/client-payments", tags=["Client Payments 客戶帳務"])
_CorrelationHeader = Annotated[
    str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
]
_IdempotencyHeader = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
]


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


@router.get(
    "/historical-payments/{case_no}",
    response_model=BaseResponse[HistoricalClientPaymentQueryView],
)
def query_historical_client_payment(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_admin),
    application: HistoricalClientPaymentWorkflow = Depends(
        get_historical_client_payment_workflow
    ),
):
    del principal
    return _historical_call(
        lambda: _historical_client_query_view(application.query(case_no)),
        "成功取得歷史客戶付款候選",
        CorrelationId(f"historical-client-query:{case_no}"),
    )


@router.post(
    "/historical-payments/preview",
    response_model=BaseResponse[HistoricalClientPaymentPreviewView],
)
def preview_historical_client_payment(
    body: HistoricalClientPaymentIntentBody,
    principal: AdminPrincipal = Depends(require_admin),
    application: HistoricalClientPaymentWorkflow = Depends(
        get_historical_client_payment_workflow
    ),
):
    del principal
    correlation = CorrelationId(f"historical-client-preview:{body.case_no}")
    return _historical_call(
        lambda: _historical_client_preview_view(application.preview(_historical_client_intent(body))),
        "成功預覽歷史客戶付款確認",
        correlation,
    )


@router.post(
    "/historical-payments/apply",
    response_model=BaseResponse[HistoricalClientPaymentReceiptView],
)
def apply_historical_client_payment(
    body: HistoricalClientPaymentApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_admin),
    application: HistoricalClientPaymentWorkflow = Depends(
        get_historical_client_payment_workflow
    ),
):
    correlation = CorrelationId(correlation_id)
    return _historical_call(
        lambda: _historical_client_receipt_view(
            application.apply(
                ApplyHistoricalClientPayment(
                    _historical_client_intent(body),
                    ExpectedVersion(body.expected_account_version),
                    body.expected_adoption_receipt_id,
                    PreviewFingerprint(body.preview_fingerprint),
                    IdempotencyKey(idempotency_key),
                    ActorContext(str(principal.username or "").strip()),
                    body.reason.strip(),
                    correlation,
                )
            )
        ),
        "歷史客戶付款確認已提交",
        correlation,
    )


@router.get(
    "/historical-payments/{case_no}/readback",
    response_model=BaseResponse[HistoricalClientPaymentReadbackView],
)
def readback_historical_client_payment(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_admin),
    application: HistoricalClientPaymentWorkflow = Depends(
        get_historical_client_payment_workflow
    ),
):
    del principal
    return _historical_call(
        lambda: _historical_client_readback_view(application.readback(case_no)),
        "成功重新讀取歷史客戶付款狀態",
        CorrelationId(f"historical-client-readback:{case_no}"),
    )


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


def _historical_client_intent(body: HistoricalClientPaymentIntentBody):
    return HistoricalClientPaymentIntent(
        body.case_no,
        HistoricalClientDirection(body.direction),
        HistoricalClientConfirmationKind(body.confirmation_kind),
        tuple(body.obligation_identities),
        body.payment_date,
        body.payment_date_unknown_reason,
        HistoricalClientSourceAvailability(body.source_availability),
        body.evidence_reference,
    )


def _historical_client_obligation_view(item):
    return HistoricalClientObligationView(
        obligation_identity=item.identity,
        case_no=item.case_no,
        obligation_type=item.obligation_type,
        direction=item.direction.value,
        amount_due_ntd=item.amount_due_ntd,
        projection_version=item.projection_version,
        status=item.status,
    )


def _historical_client_query_view(facts):
    return HistoricalClientPaymentQueryView(
        case_no=facts.case_no,
        account_version=facts.account_version,
        adoption_receipt_id=facts.adoption_receipt_id,
        adopted=facts.adopted,
        normal_bank_candidate_identities=list(facts.normal_bank_candidate_identities),
        obligations=[_historical_client_obligation_view(item) for item in facts.obligations],
    )


def _historical_client_preview_view(preview):
    candidate = preview.candidate
    return HistoricalClientPaymentPreviewView(
        case_no=candidate.intent.case_no,
        account_version=candidate.account_version,
        adoption_receipt_id=candidate.adoption_receipt_id,
        obligations=[_historical_client_obligation_view(item) for item in candidate.obligations],
        amount_snapshot_ntd=candidate.amount_snapshot_ntd,
        blockers=list(candidate.blockers),
        can_apply=candidate.can_apply,
        preview_fingerprint=candidate.fingerprint.value,
    )


def _historical_client_receipt_view(receipt):
    return HistoricalClientPaymentReceiptView(
        event_identity=receipt.event_identity,
        case_no=receipt.case_no,
        obligation_identities=list(receipt.obligation_identities),
        amount_snapshot_ntd=receipt.amount_snapshot_ntd,
        resulting_account_version=receipt.resulting_account_version,
        preview_fingerprint=receipt.preview_fingerprint.value,
    )


def _historical_client_readback_view(readback):
    return HistoricalClientPaymentReadbackView(
        case_no=readback.facts.case_no,
        account_version=readback.facts.account_version,
        obligations=[
            _historical_client_obligation_view(item) for item in readback.facts.obligations
        ],
        projections=[
            HistoricalClientPaymentProjectionView(
                obligation_identity=item.obligation_identity,
                amount_snapshot_ntd=item.amount_snapshot_ntd,
                obligation_projection_version=item.obligation_projection_version,
            )
            for item in readback.projections
        ],
        owner_terminal=readback.owner_terminal,
    )


def _historical_call(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except HistoricalClientPaymentError as error:
        status_code = {
            ErrorCategory.VALIDATION: 422,
            ErrorCategory.FORBIDDEN: 403,
            ErrorCategory.NOT_FOUND: 404,
            ErrorCategory.DOMAIN_BLOCKED: 409,
            ErrorCategory.CONFLICT: 409,
            ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
            ErrorCategory.UNAVAILABLE: 503,
            ErrorCategory.INTERNAL: 500,
        }[error.error.category]
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": {
                    "category": error.error.category.value,
                    "code": error.error.code,
                    "message": error.error.message,
                    "correlation_id": error.error.correlation_id.value,
                    "domain_blockers": list(error.error.domain_blockers),
                    "retryable": error.error.retryable,
                    "current_version": (
                        None
                        if error.error.current_version is None
                        else error.error.current_version.value
                    ),
                }
            },
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "category": "validation",
                    "code": str(error) or "historical_client_payment_invalid",
                    "message": "歷史客戶付款請求未通過驗證。",
                    "correlation_id": correlation_id.value,
                }
            },
        ) from error

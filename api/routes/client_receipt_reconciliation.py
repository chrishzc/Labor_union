"""Authenticated typed endpoints for Client Receipt reconciliation."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.client_receipt_reconciliation import (
    ClientReceiptReconciliationApplication,
    get_client_receipt_reconciliation_application,
)
from api.schemas.base import BaseResponse
from api.schemas.client_receipt_reconciliation import (
    ClientReceiptApplyBody,
    ClientReceiptPreviewBody,
    ClientReceiptPreviewView,
    ClientReceiptQueryView,
    ClientReceiptReceiptView,
)
from domains.client_finance.error_contract import (
    canonicalize_client_finance_error,
)
from domains.client_finance.reconciliation import PaymentStage
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    ClientReceiptRepositoryUnavailable,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationError,
    ReconciliationSelection,
)

router = APIRouter(
    prefix="/api/v1/orders/{case_no}/client-finance/receipt-reconciliation",
    tags=["Client Finance"],
)
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


@router.get("", response_model=BaseResponse[ClientReceiptQueryView])
def query_receipt_facts(
    case_no: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientReceiptReconciliationApplication = Depends(
        get_client_receipt_reconciliation_application
    ),
):
    del principal
    correlation = CorrelationId(f"client-receipt-query:{case_no}")
    return _call(
        lambda: application.query(case_no),
        "成功取得客戶收款根事實",
        correlation,
    )


@router.post(
    "/preview",
    response_model=BaseResponse[ClientReceiptPreviewView],
)
def preview_receipt(
    body: ClientReceiptPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-receipt-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientReceiptReconciliationApplication = Depends(
        get_client_receipt_reconciliation_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(application.preview(_selection(case_no, body))),
        "成功產生客戶收款核銷預覽",
        correlation,
    )


@router.post(
    "/apply",
    response_model=BaseResponse[ClientReceiptReceiptView],
)
# Kept cohesive because FastAPI must expose the full authenticated command edge.
def apply_receipt(
    body: ClientReceiptApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientReceiptReconciliationApplication = Depends(
        get_client_receipt_reconciliation_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    case_no,
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "成功套用客戶收款核銷",
        correlation,
    )


@router.post(
    "/overage/preview",
    response_model=BaseResponse[ClientReceiptPreviewView],
)
def preview_receipt_overage(
    body: ClientReceiptPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-receipt-overage-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientReceiptReconciliationApplication = Depends(
        get_client_receipt_reconciliation_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_selection(case_no, body, allow_overage_disposition=True))
        ),
        "成功產生客戶超收處置預覽",
        correlation,
    )


@router.post(
    "/overage/apply",
    response_model=BaseResponse[ClientReceiptReceiptView],
)
def apply_receipt_overage(
    body: ClientReceiptApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientReceiptReconciliationApplication = Depends(
        get_client_receipt_reconciliation_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    case_no,
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                    allow_overage_disposition=True,
                )
            )
        ),
        "已確認實收並建立客戶退款應付",
        correlation,
    )


def _selection(case_no, body, *, allow_overage_disposition=False) -> ReconciliationSelection:
    row_ids = tuple(str(value) for value in body.finance_import_row_ids)
    obligations = tuple(value.strip() for value in body.obligation_identities)
    _require_unique(row_ids)
    _require_unique(obligations)
    if any(not value for value in obligations):
        raise ValueError("invalid_client_receipt_intent")
    return ReconciliationSelection(
        case_no.strip(),
        PaymentStage(body.payment_stage),
        tuple(sorted(row_ids, key=int)),
        tuple(sorted(obligations)),
        allow_overage_disposition,
    )


def _apply_request(
    case_no,
    body,
    key,
    correlation,
    principal,
    *,
    allow_overage_disposition=False,
):
    actor_id = str(principal.username or "").strip()
    return ClientReconciliationApplyRequest(
        _selection(case_no, body, allow_overage_disposition=allow_overage_disposition),
        ExpectedVersion(body.expected_account_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(actor_id),
        body.reason.strip(),
        correlation,
    )


def _preview_payload(preview):
    return {
        "account_version": preview.account_version,
        "candidate": _materialize(preview.candidate),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _require_unique(values) -> None:
    if len(values) != len(set(values)):
        raise ValueError("invalid_client_receipt_intent")


def _call(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except ClientReconciliationError as error:
        _raise_typed(error.error)
    except ClientReceiptRepositoryUnavailable as error:
        _raise_unavailable(error, correlation)
    except OperationalError as error:
        _raise_mysql(error, correlation)
    except ValueError as error:
        _raise_validation(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation) from error


def _raise_typed(error: TypedError) -> None:
    error = canonicalize_client_finance_error(error)
    status = {
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.FORBIDDEN: 403,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.UNAVAILABLE: 503,
        ErrorCategory.INTERNAL: 500,
    }[error.category]
    headers = {"Retry-After": "1"} if error.retryable else None
    raise _http_error(status, error, headers)


def _raise_unavailable(error, correlation):
    typed = TypedError(
        ErrorCategory.UNAVAILABLE,
        "client_receipt_temporarily_unavailable",
        "客戶收款核銷暫時無法完成，請保留相同冪等鍵重試。",
        correlation,
        retryable=True,
    )
    raise _http_error(503, typed, {"Retry-After": "1"}) from error


def _raise_mysql(error, correlation):
    retryable = bool(error.args and int(error.args[0]) in {1205, 1213})
    category = ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL
    typed = TypedError(
        category,
        "transaction_failed",
        "客戶收款核銷資料庫交易失敗。",
        correlation,
        retryable=retryable,
    )
    headers = {"Retry-After": "1"} if retryable else None
    raise _http_error(503 if retryable else 500, typed, headers) from error


def _raise_validation(error, correlation):
    typed = TypedError(
        ErrorCategory.VALIDATION,
        str(error) or "invalid_client_receipt_intent",
        "客戶收款核銷請求未通過驗證。",
        correlation,
    )
    raise _http_error(422, typed) from error


def _internal_error(correlation):
    typed = TypedError(
        ErrorCategory.INTERNAL,
        "transaction_failed",
        "客戶收款核銷交易失敗。",
        correlation,
    )
    return _http_error(500, typed)


def _http_error(status, error, headers=None):
    return HTTPException(
        status_code=status,
        detail={"error": _materialize(error)},
        headers=headers,
    )


# Kept recursive so every typed HTTP payload uses one serialization rule.
def _materialize(value):
    if isinstance(
        value,
        (CorrelationId, ExpectedVersion, IdempotencyKey, PreviewFingerprint),
    ):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _materialize(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value


__all__ = ["router"]

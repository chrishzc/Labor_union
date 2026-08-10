"""Authenticated typed endpoints for canonical deposit reversal."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.client_deposit_reversal import (
    ClientDepositReversalApplication,
    get_client_deposit_reversal_application,
)
from api.schemas.base import BaseResponse
from api.schemas.client_deposit_reversal import (
    DepositReversalApplyBody,
    DepositReversalPreviewBody,
    DepositReversalPreviewView,
    DepositReversalReceiptView,
)
from domains.client_finance.error_contract import canonicalize_client_finance_error
from infrastructure.mysql.client_deposit_reversal_repository import (
    ClientDepositReversalRepositoryUnavailable,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.deposit_reversal_workflow import (
    DepositReversalApplyRequest,
    DepositReversalError,
    DepositReversalSelection,
)


router = APIRouter(
    prefix="/api/v1/orders/{case_no}/client-finance/deposit-reversal",
    tags=["Client Finance"],
)
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]


@router.post("/preview", response_model=BaseResponse[DepositReversalPreviewView])
def preview_deposit_reversal(
    body: DepositReversalPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: _CorrelationHeader = "deposit-reversal-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientDepositReversalApplication = Depends(get_client_deposit_reversal_application),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(application.preview(_selection(case_no, body))),
        "成功產生訂金沖正預覽",
        correlation,
    )


@router.post("/apply", response_model=BaseResponse[DepositReversalReceiptView])
def apply_deposit_reversal(
    body: DepositReversalApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientDepositReversalApplication = Depends(get_client_deposit_reversal_application),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(application.apply(_request(case_no, body, idempotency_key, correlation, principal))),
        "成功套用訂金沖正",
        correlation,
    )


def _selection(case_no, body):
    return DepositReversalSelection(
        case_no.strip(), body.original_ledger_entry_id, body.reversal_occurred_on
    )


def _request(case_no, body, key, correlation, principal):
    return DepositReversalApplyRequest(
        _selection(case_no, body),
        ExpectedVersion(body.expected_account_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        correlation,
    )


def _preview_payload(preview):
    return {
        "account_version": preview.account_version,
        "candidate": _materialize(preview.candidate),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _call(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except DepositReversalError as error:
        _raise_typed(error.error)
    except ClientDepositReversalRepositoryUnavailable as error:
        _raise_http(503, TypedError(ErrorCategory.UNAVAILABLE, "deposit_reversal_temporarily_unavailable", "訂金沖正暫時無法完成，請保留相同冪等鍵重試。", correlation, retryable=True), {"Retry-After": "1"})
    except ValueError as error:
        _raise_http(422, TypedError(ErrorCategory.VALIDATION, str(error) or "invalid_deposit_reversal", "訂金沖正請求未通過驗證。", correlation))
    except HTTPException:
        raise
    except Exception as error:
        raise _http(500, TypedError(ErrorCategory.INTERNAL, "transaction_failed", "訂金沖正交易失敗。", correlation)) from error


def _raise_typed(error):
    error = canonicalize_client_finance_error(error)
    status = 409 if error.category in {ErrorCategory.CONFLICT, ErrorCategory.IDEMPOTENCY_MISMATCH, ErrorCategory.DOMAIN_BLOCKED} else 422
    _raise_http(status, error)


def _raise_http(status, error, headers=None):
    raise _http(status, error, headers)


def _http(status, error, headers=None):
    return HTTPException(status_code=status, detail={"error": _materialize(error)}, headers=headers)


def _materialize(value):
    if isinstance(value, (CorrelationId, ExpectedVersion, IdempotencyKey, PreviewFingerprint)):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _materialize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value

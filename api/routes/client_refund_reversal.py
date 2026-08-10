"""Authenticated typed endpoints for Client Refund and Client Reversal."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.client_refund_reversal import (
    ClientRefundReversalApplication,
    get_client_refund_reversal_application,
)
from api.schemas.base import BaseResponse
from api.schemas.client_refund_reversal import (
    ClientRefundApplyBody,
    ClientRefundPreviewBody,
    ClientRefundReversalPreviewView,
    ClientRefundReversalQueryView,
    ClientRefundReversalReceiptView,
    ClientRefundReturnApplyBody,
    ClientRefundReturnPreviewBody,
    ClientReversalApplyBody,
    ClientReversalPreviewBody,
)
from domains.client_finance.error_contract import (
    canonicalize_client_finance_error,
)
from domains.client_finance.client_refund_reversal import (
    ClientFinanceCorrectionType,
    ClientRefundPurpose,
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
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalApplyRequest,
    ClientRefundReversalError,
    ClientRefundReversalSelection,
)

router = APIRouter(
    prefix="/api/v1/orders/{case_no}/client-finance",
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


@router.get(
    "/refund-reversal",
    response_model=BaseResponse[ClientRefundReversalQueryView],
)
def query_refund_reversal(
    case_no: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(f"client-refund-reversal-query:{case_no}")
    return _call(lambda: application.query(case_no), "成功取得退款與沖正根事實", correlation)


@router.post(
    "/refund/preview",
    response_model=BaseResponse[ClientRefundReversalPreviewView],
)
def preview_refund(
    body: ClientRefundPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-refund-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_refund_selection(case_no, body), correlation)
        ),
        "成功產生客戶退款預覽",
        correlation,
    )


@router.post(
    "/refund/apply",
    response_model=BaseResponse[ClientRefundReversalReceiptView],
)
# Kept cohesive because FastAPI must expose the full authenticated command edge.
def apply_refund(
    body: ClientRefundApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    _refund_selection(case_no, body),
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "成功套用客戶退款",
        correlation,
    )


@router.post(
    "/subsidy-return/preview",
    response_model=BaseResponse[ClientRefundReversalPreviewView],
)
# Kept cohesive because FastAPI must expose the complete authenticated intent edge.
def preview_subsidy_return(
    body: ClientRefundPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-subsidy-return-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    selection = _refund_selection(
        case_no,
        body,
        ClientRefundPurpose.SUBSIDY_RETURN,
    )
    return _call(
        lambda: _preview_payload(application.preview(selection, correlation)),
        "成功產生客戶補助退還預覽",
        correlation,
    )


@router.post(
    "/subsidy-return/apply",
    response_model=BaseResponse[ClientRefundReversalReceiptView],
)
# Kept cohesive because FastAPI must expose the full authenticated command edge.
def apply_subsidy_return(
    body: ClientRefundApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    correlation = CorrelationId(correlation_id)
    selection = _refund_selection(
        case_no,
        body,
        ClientRefundPurpose.SUBSIDY_RETURN,
    )
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    selection,
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "成功套用客戶補助退還",
        correlation,
    )


@router.post(
    "/refund-return/preview",
    response_model=BaseResponse[ClientRefundReversalPreviewView],
)
def preview_refund_return(
    body: ClientRefundReturnPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-refund-return-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_refund_return_selection(case_no, body), correlation)
        ),
        "成功產生客戶退款退匯預覽",
        correlation,
    )


@router.post(
    "/refund-return/apply",
    response_model=BaseResponse[ClientRefundReversalReceiptView],
)
def apply_refund_return(
    body: ClientRefundReturnApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    _refund_return_selection(case_no, body),
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "成功套用客戶退款退匯",
        correlation,
    )


@router.post(
    "/reversal/preview",
    response_model=BaseResponse[ClientRefundReversalPreviewView],
)
def preview_reversal(
    body: ClientReversalPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-reversal-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_reversal_selection(case_no, body), correlation)
        ),
        "成功產生客戶收款沖正預覽",
        correlation,
    )


@router.post(
    "/reversal/apply",
    response_model=BaseResponse[ClientRefundReversalReceiptView],
)
# Kept cohesive because FastAPI must expose the full authenticated command edge.
def apply_reversal(
    body: ClientReversalApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    _reversal_selection(case_no, body),
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "成功套用客戶收款沖正",
        correlation,
    )


def _refund_selection(
    case_no,
    body,
    refund_purpose=ClientRefundPurpose.CUSTOMER_REFUND,
):
    bank_ids = _canonical_integer_identities(body.finance_import_row_ids)
    obligation_ids = _canonical_text_identities(body.obligation_identities)
    return ClientRefundReversalSelection(
        case_no.strip(),
        ClientFinanceCorrectionType.REFUND,
        refund_purpose,
        bank_fact_identities=bank_ids,
        obligation_identities=obligation_ids,
    )


def _reversal_selection(case_no, body):
    return ClientRefundReversalSelection(
        case_no.strip(),
        ClientFinanceCorrectionType.REVERSAL,
        reversal_target_identities=_canonical_integer_identities(
            body.ledger_entry_ids
        ),
        reversal_occurred_on=body.occurred_on.isoformat(),
    )


def _refund_return_selection(case_no, body):
    return ClientRefundReversalSelection(
        case_no.strip(),
        ClientFinanceCorrectionType.REFUND_RETURN,
        bank_fact_identities=(str(body.finance_import_row_id),),
        reversal_target_identities=(str(body.refund_ledger_entry_id),),
    )


def _apply_request(selection, body, key, correlation, principal):
    return ClientRefundReversalApplyRequest(
        selection,
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


def _canonical_integer_identities(values):
    identities = tuple(str(value) for value in values)
    _require_unique(identities)
    return tuple(sorted(identities, key=int))


def _canonical_text_identities(values):
    identities = tuple(value.strip() for value in values)
    if any(not value for value in identities):
        raise ValueError("invalid_client_finance_intent")
    _require_unique(identities)
    return tuple(sorted(identities))


def _require_unique(values) -> None:
    if len(values) != len(set(values)):
        raise ValueError("invalid_client_finance_intent")


# Kept cohesive so every endpoint returns the same typed error envelope.
def _call(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except ClientRefundReversalError as error:
        _raise_typed(error.error)
    except ValueError as error:
        _raise_value_error(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        typed = TypedError(
            ErrorCategory.INTERNAL,
            "transaction_failed",
            "客戶退款或沖正交易失敗。",
            correlation,
        )
        raise _http_error(500, typed) from error


def _raise_typed(error):
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


def _raise_value_error(error, correlation):
    code = str(error) or "invalid_client_finance_intent"
    if code in {"client_finance_case_not_found", "client_obligation_not_found"}:
        category, status = ErrorCategory.NOT_FOUND, 404
    elif code == "invalid_client_finance_intent":
        category, status = ErrorCategory.VALIDATION, 422
    else:
        category, status = ErrorCategory.DOMAIN_BLOCKED, 409
    typed = TypedError(
        category,
        code,
        "客戶退款或沖正請求未通過驗證。",
        correlation,
        domain_blockers=(code,) if status == 409 else (),
    )
    raise _http_error(status, typed) from error


def _http_error(status, error, headers=None):
    return HTTPException(
        status_code=status,
        detail={"error": _materialize(error)},
        headers=headers,
    )


# Kept recursive so every typed HTTP payload uses one serialization rule.
def _materialize(value):
    if hasattr(value, "value") and value.__class__.__module__.startswith(
        ("shared_kernel.",)
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

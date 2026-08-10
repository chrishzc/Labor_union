"""Authenticated typed endpoints for conserved financial adjustments."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.financial_adjustment import (
    FinancialAdjustmentApplication,
    get_financial_adjustment_application,
)
from api.schemas.base import BaseResponse
from api.schemas.financial_adjustment import (
    FinancialAdjustmentApplyBody,
    FinancialAdjustmentPreviewBody,
    FinancialAdjustmentPreviewView,
    FinancialAdjustmentQueryView,
    FinancialAdjustmentReceiptView,
)
from domains.client_finance.error_contract import (
    canonicalize_client_finance_error,
)
from domains.client_finance.financial_adjustment import (
    FinancialAdjustmentAllocationIntent,
    FinancialAdjustmentIntent,
    FinancialAdjustmentScope,
    FinancialAdjustmentSource,
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
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.financial_adjustment_workflow import (
    FinancialAdjustmentApplyRequest,
    FinancialAdjustmentError,
)

router = APIRouter(
    prefix="/api/v1/orders/{case_no}/client-finance/adjustments",
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


@router.get("", response_model=BaseResponse[FinancialAdjustmentQueryView])
def query_financial_adjustments(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: FinancialAdjustmentApplication = Depends(
        get_financial_adjustment_application
    ),
):
    del principal
    correlation = CorrelationId(f"financial-adjustment-query:{case_no}")
    return _call(
        lambda: application.query(case_no.strip()),
        "成功取得共用財務調整",
        correlation,
    )


@router.post(
    "/manual-extra/preview",
    response_model=BaseResponse[FinancialAdjustmentPreviewView],
)
def preview_manual_financial_adjustment(
    body: FinancialAdjustmentPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: _CorrelationHeader = "financial-adjustment-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: FinancialAdjustmentApplication = Depends(
        get_financial_adjustment_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_intent(case_no, body), correlation)
        ),
        "成功產生共用財務調整 Preview",
        correlation,
    )


@router.post(
    "/manual-extra/apply",
    response_model=BaseResponse[FinancialAdjustmentReceiptView],
)
# Kept cohesive because FastAPI must expose one authenticated atomic command edge.
def apply_manual_financial_adjustment(
    body: FinancialAdjustmentApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: FinancialAdjustmentApplication = Depends(
        get_financial_adjustment_application
    ),
):
    correlation = CorrelationId(correlation_id)
    request = FinancialAdjustmentApplyRequest(
        _intent(case_no, body),
        ExpectedVersion(body.expected_client_account_version),
        _expected_payroll_version(body.expected_payroll_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        correlation,
    )
    return _call(
        lambda: _materialize(application.apply(request)),
        "成功套用共用財務調整",
        correlation,
    )


# Kept whole so one HTTP body maps deterministically to one Domain intent.
def _intent(case_no, body):
    allocations = tuple(
        sorted(
            (
                FinancialAdjustmentAllocationIntent(
                    item.assignment_id,
                    MoneyNTD(item.amount_delta_ntd),
                )
                for item in body.assignment_allocations
            ),
            key=lambda item: item.assignment_id,
        )
    )
    return FinancialAdjustmentIntent(
        case_no.strip(),
        FinancialAdjustmentSource.MANUAL_EXTRA,
        body.source_event_identity.strip(),
        MoneyNTD(body.amount_delta_ntd),
        allocations,
        body.reason.strip(),
        _optional_text(body.reversal_of_adjustment_identity),
        FinancialAdjustmentScope(body.scope),
    )


def _expected_payroll_version(value):
    return None if value is None else ExpectedVersion(value)


def _optional_text(value):
    return value.strip() if isinstance(value, str) else None


def _preview_payload(preview):
    return {
        "client_account_version": preview.client_account_version,
        "payroll_version": preview.payroll_version,
        "candidate": _materialize(preview.candidate),
        "preview_fingerprint": preview.fingerprint.value,
    }


# Kept cohesive so every endpoint returns the same typed error envelope.
def _call(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except FinancialAdjustmentError as error:
        _raise_typed(error.error)
    except ValueError as error:
        _raise_value_error(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        typed = TypedError(
            ErrorCategory.INTERNAL,
            "transaction_failed",
            "共用財務調整交易失敗。",
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
    code = str(error) or "invalid_financial_adjustment_facts"
    category = (
        ErrorCategory.NOT_FOUND
        if code == "client_finance_case_not_found"
        else ErrorCategory.VALIDATION
    )
    status = 404 if category is ErrorCategory.NOT_FOUND else 422
    typed = TypedError(
        category,
        code,
        "共用財務調整請求未通過驗證。",
        correlation,
    )
    raise _http_error(status, typed) from error


def _http_error(status, error, headers=None):
    return HTTPException(
        status_code=status,
        detail={"error": _materialize(error)},
        headers=headers,
    )


# Kept recursive so all typed HTTP payloads use one serialization rule.
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

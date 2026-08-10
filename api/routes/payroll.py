"""Authenticated typed HTTP endpoints for Payroll queries and adjustments."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.payroll import PayrollApplication, get_payroll_application
from api.schemas.base import BaseResponse
from api.schemas.payroll import (
    CasePayrollQueryView,
    PayrollAdjustmentApplyBody,
    PayrollAdjustmentPreviewBody,
    PayrollAdjustmentPreviewView,
    PayrollAdjustmentReceiptView,
    StaffPayrollObligationsQueryView,
)
from domains.payroll.adjustment import (
    PayrollAdjustmentAllocationIntent,
    PayrollAdjustmentIntent,
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
from subsystems.payroll.adjustment_workflow import (
    PayrollAdjustmentApplyRequest,
    PayrollAdjustmentError,
)

router = APIRouter(prefix="/api/v1/payroll", tags=["Payroll"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


@router.get(
    "/cases/{case_no}",
    response_model=BaseResponse[CasePayrollQueryView],
)
def query_case_payroll(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: PayrollApplication = Depends(get_payroll_application),
):
    del principal
    return _call_endpoint(
        lambda: application.query_case(case_no),
        "成功取得訂單薪資義務",
        CorrelationId(f"payroll-case-query:{case_no}"),
    )


@router.get(
    "/staff/{staff_id}/obligations",
    response_model=BaseResponse[StaffPayrollObligationsQueryView],
)
def query_staff_payroll_obligations(
    staff_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: PayrollApplication = Depends(get_payroll_application),
):
    del principal
    return _call_endpoint(
        lambda: application.query_staff(staff_id),
        "成功取得月嫂薪資義務",
        CorrelationId(f"payroll-staff-query:{staff_id}"),
    )


@router.post(
    "/adjustments/preview",
    response_model=BaseResponse[PayrollAdjustmentPreviewView],
)
def preview_staff_payroll_adjustment(
    body: PayrollAdjustmentPreviewBody,
    correlation_id: _CorrelationHeader = "payroll-adjustment-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: PayrollApplication = Depends(get_payroll_application),
):
    del principal
    return _call_endpoint(
        lambda: _preview_payload(
            application.preview(
                _intent(body),
                CorrelationId(correlation_id),
            )
        ),
        "成功產生薪資調整 Preview",
        CorrelationId(correlation_id),
    )


# Kept whole so the authenticated actor and both command headers stay auditable.
@router.post(
    "/adjustments/apply",
    response_model=BaseResponse[PayrollAdjustmentReceiptView],
)
def apply_staff_payroll_adjustment(
    body: PayrollAdjustmentApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: PayrollApplication = Depends(get_payroll_application),
):
    return _call_endpoint(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    body,
                    idempotency_key,
                    correlation_id,
                    principal,
                )
            )
        ),
        "成功套用薪資調整",
        CorrelationId(correlation_id),
    )


def _intent(body):
    allocations = tuple(
        PayrollAdjustmentAllocationIntent(
            item.assignment_id,
            MoneyNTD(item.amount_ntd),
        )
        for item in sorted(body.allocations, key=lambda item: item.assignment_id)
    )
    return PayrollAdjustmentIntent(
        body.case_no.strip(),
        body.source_event_identity.strip(),
        allocations,
    )


def _apply_request(body, key, correlation_id, principal):
    return PayrollAdjustmentApplyRequest(
        _intent(body),
        ExpectedVersion(body.expected_payroll_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        CorrelationId(correlation_id),
    )


def _preview_payload(preview):
    candidate = preview.candidate
    return {
        "payroll_version": preview.payroll_version,
        "candidate": {
            "case_no": candidate.case_no,
            "source_event_identity": candidate.source_event_identity,
            "adjustment_identity": candidate.adjustment_identity,
            "amount_ntd": candidate.amount.amount,
            "due_date": candidate.due_date,
            "allocations": [
                _allocation_payload(item) for item in candidate.allocations
            ],
            "candidate_fingerprint": candidate.fingerprint.value,
        },
        "preview_fingerprint": preview.fingerprint.value,
    }


def _allocation_payload(allocation):
    return {
        "assignment_id": allocation.assignment_id,
        "staff_id": allocation.staff_id,
        "signed_amount_ntd": allocation.signed_amount.amount,
        "obligation_identity": allocation.obligation_identity,
        "obligation_kind": allocation.obligation_kind.value,
        "direction": allocation.direction.value,
        "amount_due_ntd": allocation.amount_due.amount,
        "source_obligation_identity": allocation.source_obligation_identity,
        "payout_history_exists": allocation.payout_history_exists,
    }


def _call_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except PayrollAdjustmentError as error:
        _raise_typed_error(error.error)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except (TypeError, ValueError) as error:
        _raise_validation_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


def _raise_typed_error(error):
    status_code = {
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
    raise _http_error(status_code, error, headers=headers)


def _raise_mysql_error(error, correlation_id):
    mysql_code = int(error.args[0]) if error.args else 0
    retryable = mysql_code in _RETRYABLE_MYSQL_CODES
    typed = TypedError(
        ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
        "transaction_failed",
        "Payroll 交易暫時無法完成。" if retryable else "Payroll 交易失敗。",
        correlation_id,
        retryable=retryable,
    )
    headers = {"Retry-After": "1"} if retryable else None
    raise _http_error(503 if retryable else 500, typed, headers=headers)


def _raise_validation_error(error, correlation_id):
    typed = TypedError(
        ErrorCategory.VALIDATION,
        str(error) or "invalid_payroll_facts",
        "Payroll 調整請求未通過驗證。",
        correlation_id,
    )
    raise _http_error(422, typed)


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "transaction_failed",
            "Payroll 交易失敗。",
            correlation_id,
        ),
    )


def _http_error(status_code, error, *, headers=None):
    return HTTPException(
        status_code=status_code,
        detail={"error": _materialize(error)},
        headers=headers,
    )


def _materialize(value):
    if isinstance(
        value,
        (CorrelationId, ExpectedVersion, IdempotencyKey, PreviewFingerprint),
    ):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _materialize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value


__all__ = ["router"]

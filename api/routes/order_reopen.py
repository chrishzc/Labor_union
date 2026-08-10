"""Typed Preview and Apply endpoints for controlled order reopening."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_reopen import (
    OrderReopenApplication,
    get_order_reopen_application,
)
from api.schemas.base import BaseResponse
from api.schemas.order_reopen import (
    OrderReopenPreviewView,
    OrderReopenReceiptView,
)
from domains.orders.reopen import ReopenCandidateError
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.orders.reopen_workflow import (
    OrderReopenApplyRequest,
    ReopenWorkflowError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["Order Reopen"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class OrderReopenApplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_order_version: int = Field(ge=0)
    expected_client_finance_version: int = Field(ge=0)
    expected_payroll_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


@router.post(
    "/{case_no}/reopen/preview",
    response_model=BaseResponse[OrderReopenPreviewView],
)
def preview_order_reopen(
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "order-reopen-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderReopenApplication = Depends(
        get_order_reopen_application
    ),
):
    del principal
    identity = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _preview_payload(application.preview(case_no)),
        "成功產生訂單受控重開預覽",
        identity,
    )


@router.post(
    "/{case_no}/reopen/apply",
    response_model=BaseResponse[OrderReopenReceiptView],
)
# FastAPI requires the complete HTTP contract on this callable.
def apply_order_reopen(
    body: OrderReopenApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderReopenApplication = Depends(
        get_order_reopen_application
    ),
):
    request = _apply_request(
        case_no,
        body,
        idempotency_key,
        correlation_id,
        principal,
    )
    return _call_endpoint(
        lambda: _materialize(application.apply(request)),
        "成功套用訂單受控重開",
        request.correlation_id,
    )


def _apply_request(case_no, body, key, correlation, principal):
    return OrderReopenApplyRequest(
        case_no,
        ExpectedVersion(body.expected_order_version),
        ExpectedVersion(body.expected_client_finance_version),
        ExpectedVersion(body.expected_payroll_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(str(principal.username or "").strip()),
        body.reason,
        CorrelationId(correlation),
    )


def _preview_payload(preview):
    candidate = preview.candidate
    return {
        "after_status": candidate.after_status.value,
        "before_status": candidate.before_status.value,
        "cancellation_event_id": candidate.cancellation_event_id,
        "case_no": candidate.case_no,
        "client_finance_version": preview.client_finance_version,
        "order_version": candidate.expected_order_version,
        "payroll_version": preview.payroll_version,
        "preview_fingerprint": preview.fingerprint.value,
        "requires_fresh_scheduling_preview": (
            candidate.requires_fresh_scheduling_preview
        ),
        "restored_assignment_ids": list(candidate.restored_assignment_ids),
        "restored_lock_ids": list(candidate.restored_lock_ids),
        "restored_schedule_ids": list(candidate.restored_schedule_ids),
    }


def _call_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except ReopenWorkflowError as error:
        _raise_typed_error(error.error)
    except ReopenCandidateError as error:
        _raise_candidate_error(error, correlation_id)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except ValueError as error:
        _raise_value_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


def _raise_candidate_error(error, correlation_id):
    code = error.blocker.value
    typed = TypedError(
        ErrorCategory.DOMAIN_BLOCKED,
        code,
        "訂單目前不符合受控重開條件。",
        correlation_id,
        domain_blockers=(code,),
    )
    raise _http_error(409, typed) from error


def _raise_typed_error(error):
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
    raise _http_error(status, error, headers=headers)


def _raise_mysql_error(error, correlation_id):
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "order_reopen_transaction_temporarily_unavailable",
            "可使用相同冪等鍵重試這次受控重開。",
            correlation_id,
            retryable=True,
        )
        raise _http_error(503, typed, headers={"Retry-After": "1"}) from error
    raise _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "order_reopen_database_error",
            "訂單受控重開寫入失敗。",
            correlation_id,
        ),
    ) from error


def _raise_value_error(error, correlation_id):
    code = str(error) or "order_reopen_validation_error"
    not_found = code == "order_not_found"
    typed = TypedError(
        ErrorCategory.NOT_FOUND if not_found else ErrorCategory.VALIDATION,
        code,
        "訂單受控重開請求未通過驗證。",
        correlation_id,
    )
    raise _http_error(404 if not_found else 422, typed) from error


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "order_reopen_internal_error",
            "訂單受控重開處理失敗。",
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
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value

"""
File: order_auto_completion.py
Description: 提供 Orders 服務完成的 typed Preview 與 canonical Apply API。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_auto_completion import (
    OrderAutoCompletionApplication,
    get_order_auto_completion_application,
)
from api.schemas.base import BaseResponse
from api.schemas.order_auto_completion import (
    OrderAutoCompletionPreviewView,
    OrderAutoCompletionReceiptView,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.auto_completion_workflow import (
    AutoCompletionApplyRequest,
    AutoCompletionPreviewRequest,
    AutoCompletionWorkflowError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["Order Service Completion"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class OrderAutoCompletionApplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_order_version: int = Field(ge=0)
    evaluation_at: datetime
    reason: str = Field(min_length=1, max_length=500)
    preview_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class OrderAutoCompletionPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_at: datetime


@router.post(
    "/{case_no}/service-completion/preview",
    response_model=BaseResponse[OrderAutoCompletionPreviewView],
)
def preview_order_auto_completion(
    body: OrderAutoCompletionPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "order-auto-completion-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderAutoCompletionApplication = Depends(
        get_order_auto_completion_application
    ),
):
    del principal
    request = AutoCompletionPreviewRequest(
        case_no,
        body.evaluation_at,
        CorrelationId(correlation_id),
    )
    try:
        preview = application.preview(request)
        return BaseResponse(
            data={
                "case_no": preview.case_no,
                "expected_order_version": preview.expected_order_version,
                "resulting_order_version": preview.resulting_order_version,
                "current_status": preview.current_status,
                "completion_instant": preview.completion_instant,
                "evaluation_at": preview.evaluation_at,
                "official_service_dates": preview.official_service_dates,
                "fingerprint": preview.fingerprint.value,
            },
            message="成功產生服務完成 Preview",
        )
    except AutoCompletionWorkflowError as error:
        raise _typed_http_error(error.error) from error
    except ValueError as error:
        typed = TypedError(ErrorCategory.VALIDATION, str(error) or "auto_completion_validation_error", "服務完成 Preview 未通過驗證。", request.correlation_id)
        raise _typed_http_error(typed) from error


@router.post("/{case_no}/service-completion/apply", response_model=BaseResponse[OrderAutoCompletionReceiptView])
def apply_order_auto_completion(
    body: OrderAutoCompletionApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderAutoCompletionApplication = Depends(get_order_auto_completion_application),
):
    request = AutoCompletionApplyRequest(case_no, ExpectedVersion(body.expected_order_version), body.evaluation_at, IdempotencyKey(idempotency_key), ActorContext(str(principal.username or "").strip()), body.reason, CorrelationId(correlation_id), PreviewFingerprint(body.preview_fingerprint) if body.preview_fingerprint is not None else None)
    try:
        receipt = application.apply(request)
        return BaseResponse(
            data={
                "case_no": receipt.case_no,
                "idempotency_key": receipt.idempotency_key.value,
                "order_version": receipt.order_version,
                "lifecycle_event_id": receipt.lifecycle_event_id,
                "completion_instant": receipt.completion_instant,
                "evaluation_at": receipt.evaluation_at,
                "command_fingerprint": receipt.command_fingerprint.value,
            },
            message="成功記錄服務完成",
        )
    except AutoCompletionWorkflowError as error:
        raise _typed_http_error(error.error) from error
    except OperationalError as error:
        raise _mysql_http_error(error, request.correlation_id) from error
    except ValueError as error:
        typed = TypedError(ErrorCategory.VALIDATION, str(error) or "auto_completion_validation_error", "服務完成請求未通過驗證。", request.correlation_id)
        raise _typed_http_error(typed) from error


def _typed_http_error(error):
    status = 409 if error.category in {ErrorCategory.DOMAIN_BLOCKED, ErrorCategory.CONFLICT, ErrorCategory.IDEMPOTENCY_MISMATCH} else 422
    if error.category is ErrorCategory.UNAVAILABLE:
        status = 503
    if error.category is ErrorCategory.INTERNAL:
        status = 500
    return HTTPException(status_code=status, detail={"error": {"category": error.category.value, "code": error.code, "message": error.message, "correlation_id": error.correlation_id.value, "domain_blockers": list(error.domain_blockers)}})


def _mysql_http_error(error, correlation_id):
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "auto_completion_transaction_temporarily_unavailable",
            "Retry with the same idempotency key.",
            correlation_id,
            retryable=True,
        )
        response = _typed_http_error(typed)
        response.headers = {"Retry-After": "1"}
        return response
    typed = TypedError(
        ErrorCategory.INTERNAL,
        "auto_completion_database_error",
        "Order service completion persistence failed.",
        correlation_id,
    )
    return _typed_http_error(typed)

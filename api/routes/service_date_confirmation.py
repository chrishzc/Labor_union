"""
File: service_date_confirmation.py
Description: 提供服務日期確認的 Query、Preview 與 Apply HTTP 端點，支援冪等與型別化錯誤。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.service_date_confirmation import (
    get_service_date_confirmation_workflow,
)
from api.schemas.base import BaseResponse
from api.schemas.service_date_confirmation import (
    ServiceDateConfirmationPreviewView,
    ServiceDateConfirmationQueryView,
    ServiceDateConfirmationReceiptView,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/orders", tags=["Confirmed Service Dates"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class ServiceDatePreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_dates: list[date] = Field(min_length=1)


class ServiceDateApplyBody(ServiceDatePreviewBody):
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        trimmed = value.strip()
        if not (1 <= len(trimmed) <= 500):
            raise ValueError("reason must be 1 to 500 non-whitespace characters")
        return trimmed


@router.get(
    "/{case_no}/service-dates",
    response_model=BaseResponse[ServiceDateConfirmationQueryView],
)
def query_service_dates(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_service_date_confirmation_workflow),
):
    del principal
    return _call_endpoint(
        lambda: _query_payload(workflow.query(case_no)),
        "成功取得服務日期確認狀態",
        CorrelationId(f"service-dates-query:{case_no}"),
    )


@router.post(
    "/{case_no}/service-dates/preview",
    response_model=BaseResponse[ServiceDateConfirmationPreviewView],
)
def preview_service_dates(
    body: ServiceDatePreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "service-dates-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_service_date_confirmation_workflow),
):
    del principal
    identity = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _preview_payload(
            workflow.preview(case_no, tuple(body.service_dates))
        ),
        "成功產生服務日期確認 Preview",
        identity,
    )


@router.post(
    "/{case_no}/service-dates/apply",
    response_model=BaseResponse[ServiceDateConfirmationReceiptView],
)
def apply_service_dates(
    body: ServiceDateApplyBody,
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
    workflow=Depends(get_service_date_confirmation_workflow),
):
    identity = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _apply_payload(
            workflow.apply(
                case_no,
                tuple(body.service_dates),
                expected_order_version=body.expected_order_version,
                expected_scheduling_version=body.expected_scheduling_version,
                preview_fingerprint=body.preview_fingerprint,
                actor=str(principal.username or "").strip(),
                reason=body.reason.strip(),
                idempotency_key=idempotency_key,
            )
        ),
        "服務日期已確認",
        identity,
    )


def _query_payload(facts) -> dict[str, Any]:
    return {
        "case_no": facts.case_no,
        "order_version": facts.order_version,
        "scheduling_version": facts.scheduling_version,
        "contracted_service_days": facts.contracted_service_days,
        "suggested_dates": facts.suggested_dates,
        "selectable_dates": facts.selectable_dates,
        "current_version": facts.current_version,
        "current_dates": facts.current_dates,
    }


def _preview_payload(preview) -> dict[str, Any]:
    candidate = preview.candidate
    return {
        "case_no": candidate.case_no,
        "order_version": candidate.order_version,
        "scheduling_version": candidate.scheduling_version,
        "current_version": preview.current_version,
        "service_dates": candidate.service_dates,
        "weeks": preview.weeks,
        "preview_fingerprint": candidate.fingerprint.value,
    }


def _apply_payload(receipt) -> dict[str, Any]:
    return {
        "case_no": receipt.case_no,
        "confirmed_version": receipt.confirmed_version,
        "order_version": receipt.order_version,
        "scheduling_version": receipt.scheduling_version,
        "service_dates": receipt.service_dates,
        "preview_fingerprint": receipt.fingerprint.value,
    }


def _call_endpoint(command, message: str, correlation_id: CorrelationId):
    try:
        return BaseResponse(data=command(), message=message)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except ValueError as error:
        _raise_value_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


def _raise_typed_error(error: TypedError) -> None:
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


def _raise_mysql_error(
    error: OperationalError, correlation_id: CorrelationId
) -> None:
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "service_date_confirmation_transaction_temporarily_unavailable",
            "可使用相同冪等鍵重試這次服務日期確認。",
            correlation_id,
            retryable=True,
        )
        raise _http_error(503, typed, headers={"Retry-After": "1"}) from error
    raise _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "service_date_confirmation_database_error",
            "服務日期確認寫入失敗。",
            correlation_id,
        ),
    ) from error


def _raise_value_error(
    error: ValueError, correlation_id: CorrelationId
) -> None:
    code = str(error) or "service_date_confirmation_validation_error"
    if "not_found" in code:
        category = ErrorCategory.NOT_FOUND
        status_code = 404
        message = "找不到指定的訂單。"
    elif "idempotency_conflict" in code or "idempotency_mismatch" in code:
        category = ErrorCategory.IDEMPOTENCY_MISMATCH
        status_code = 409
        message = "相同冪等鍵已被不同內容的請求使用。"
    elif "stale" in code or "conflict" in code:
        category = ErrorCategory.CONFLICT
        status_code = 409
        message = "版本或預覽已過期，請重新查詢後重試。"
    elif "blocked" in code:
        category = ErrorCategory.DOMAIN_BLOCKED
        status_code = 409
        message = "目前狀態無法執行服務日期確認。"
    else:
        category = ErrorCategory.VALIDATION
        status_code = 422
        message = "服務日期確認請求未通過驗證。"
    typed = TypedError(
        category=category,
        code=code,
        message=message,
        correlation_id=correlation_id,
    )
    raise _http_error(status_code, typed) from error


def _internal_error(correlation_id: CorrelationId) -> HTTPException:
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "service_date_confirmation_internal_error",
            "服務日期確認處理失敗。",
            correlation_id,
        ),
    )


def _http_error(
    status_code: int,
    error: TypedError,
    *,
    headers: dict[str, str] | None = None,
) -> HTTPException:
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
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value

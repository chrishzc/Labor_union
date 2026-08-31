"""File: order_cancellation.py
Description: 提供訂單取消查詢、receipt 讀取及 Preview／Apply API。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_cancellation import (
    OrderCancellationApplication,
    get_order_cancellation_application,
)
from api.schemas.base import BaseResponse
from api.schemas.order_cancellation import (
    OrderCancellationPreviewView,
    OrderCancellationQueryView,
    OrderCancellationReceiptView,
)
from domains.orders.cancellation import (
    CancellationCandidateError,
    ConfirmedServiceDay,
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
from subsystems.orders.cancellation_workflow import (
    CancellationWorkflowError,
    OrderCancellationApplyRequest,
)

router = APIRouter(prefix="/api/v1/orders", tags=["Order Cancellation"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class CancellationServiceDayBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_date: date
    staff_id: int = Field(gt=0)
    reason: str | None = Field(default=None, min_length=1, max_length=500)


class OrderCancellationPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed_service_days: list[CancellationServiceDayBody]


class OrderCancellationApplyBody(OrderCancellationPreviewBody):
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    expected_client_finance_version: int = Field(ge=0)
    expected_payroll_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


@router.get(
    "/{case_no}/cancellation",
    response_model=BaseResponse[OrderCancellationQueryView],
)
def query_order_cancellation(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderCancellationApplication = Depends(
        get_order_cancellation_application
    ),
):
    del principal
    return _call_endpoint(
        lambda: _query_payload(application.query(case_no)),
        "成功取得訂單取消狀態",
        CorrelationId(f"query:{case_no}"),
    )


@router.get(
    "/{case_no}/cancellation/receipt",
    response_model=BaseResponse[OrderCancellationReceiptView],
)
def query_order_cancellation_receipt(
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
        max_length=191,
    ),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderCancellationApplication = Depends(
        get_order_cancellation_application
    ),
):
    del principal
    identity = CorrelationId(f"order-cancellation-receipt:{case_no}")
    return _call_endpoint(
        lambda: _materialize(
            application.query_receipt(case_no, idempotency_key)
        ),
        "成功取得訂單取消 receipt",
        identity,
    )


@router.post(
    "/{case_no}/cancellation/preview",
    response_model=BaseResponse[OrderCancellationPreviewView],
)
# FastAPI requires the complete HTTP contract on this callable for OpenAPI generation.
def preview_order_cancellation(
    body: OrderCancellationPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "order-cancellation-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderCancellationApplication = Depends(
        get_order_cancellation_application
    ),
):
    del principal
    identity = CorrelationId(correlation_id)
    confirmed_days = _confirmed_service_days(body.confirmed_service_days)
    return _call_endpoint(
        lambda: _preview_payload(
            application.preview(case_no, confirmed_days)
        ),
        "成功產生訂單取消預覽",
        identity,
    )


@router.post(
    "/{case_no}/cancellation/apply",
    response_model=BaseResponse[OrderCancellationReceiptView],
)
# FastAPI requires the complete HTTP contract on this callable for OpenAPI generation.
def apply_order_cancellation(
    body: OrderCancellationApplyBody,
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
    application: OrderCancellationApplication = Depends(
        get_order_cancellation_application
    ),
):
    request = _apply_request(
        case_no, body, idempotency_key, correlation_id, principal
    )
    return _call_endpoint(
        lambda: _materialize(application.apply(request)),
        "成功套用訂單取消",
        request.correlation_id,
    )


def _apply_request(case_no, body, key, correlation, principal):
    return OrderCancellationApplyRequest(
        case_no,
        _confirmed_service_days(body.confirmed_service_days),
        ExpectedVersion(body.expected_order_version),
        ExpectedVersion(body.expected_scheduling_version),
        ExpectedVersion(body.expected_client_finance_version),
        ExpectedVersion(body.expected_payroll_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(str(principal.username or "").strip()),
        body.reason,
        CorrelationId(correlation),
    )


def _confirmed_service_days(values):
    return tuple(
        ConfirmedServiceDay(
            item.service_date,
            item.staff_id,
            item.reason,
        )
        for item in values
    )


def _query_payload(result) -> dict[str, Any]:
    facts = result.facts
    return {
        "case_no": facts.order.case_no,
        "lifecycle_status": facts.lifecycle.current_status.value,
        "actual_start_date": facts.order.actual_start_date,
        "contracted_service_days": facts.order.contracted_service_days,
        "service_hours_per_day": facts.order.service_hours_per_day,
        "service_started": facts.order.service_started,
        "historical_mid_service_confirmation_available": (
            facts.historical_cancellation_origin
            and not facts.order.service_started
            and facts.lifecycle.current_status.value == "訂單取消"
        ),
        "service_data_locked": facts.order.service_data_locked,
        "order_version": facts.order.order_version,
        "scheduling_version": facts.scheduling.aggregate_version,
        "scheduling_generation": facts.scheduling.generation_number,
        "client_finance_version": facts.client_finance.account_version,
        "payroll_version": facts.payroll.payroll_version,
        "confirmed_service_days": _current_service_days(facts.scheduling),
        "caregiver_options": list(result.caregiver_options),
    }


def _current_service_days(scheduling):
    days = (
        {
            "service_date": service_date,
            "staff_id": assignment.staff_id,
            "reason": None,
        }
        for assignment in scheduling.assignments
        for service_date in assignment.service_dates
    )
    return sorted(days, key=lambda item: (item["service_date"], item["staff_id"]))


def _preview_payload(preview) -> dict[str, Any]:
    candidate = preview.candidate
    return {
        **_preview_business_payload(candidate),
        **_preview_version_payload(preview),
        "scheduling": _materialize(candidate.scheduling),
        "client_finance_impact": _materialize(
            preview.client_finance_impact
        ),
        "payroll_impact": _materialize(preview.payroll_impact),
        "lifecycle_impact": _materialize(preview.lifecycle_impact),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _preview_business_payload(candidate):
    return {
        "cancellation_date": candidate.cancellation_date,
        "actual_start_date": candidate.actual_start_date,
        "actual_end_date": candidate.actual_end_date,
        "confirmed_service_days": _materialize(
            candidate.confirmed_service_days
        ),
        "official_service_day_count": candidate.official_service_day_count,
        "official_service_hours": candidate.official_service_hours,
    }


def _preview_version_payload(preview):
    return {
        "order_version": preview.order_version,
        "scheduling_version": preview.scheduling_version,
        "scheduling_generation": (
            preview.candidate.scheduling.generation_number
        ),
        "client_finance_version": preview.client_finance_version,
        "payroll_version": preview.payroll_version,
    }


def _call_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except CancellationWorkflowError as error:
        _raise_typed_error(error.error)
    except CancellationCandidateError as error:
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
    blocker = error.blocker.value
    typed = TypedError(
        ErrorCategory.DOMAIN_BLOCKED,
        blocker,
        "訂單取消需要人員先處理阻擋原因。",
        correlation_id,
        domain_blockers=(blocker,),
    )
    raise _http_error(409, typed) from error


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


def _raise_mysql_error(error, correlation_id):
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "order_cancellation_transaction_temporarily_unavailable",
            "可使用相同冪等鍵重試這次訂單取消交易。",
            correlation_id,
            retryable=True,
        )
        raise _http_error(503, typed, headers={"Retry-After": "1"}) from error
    typed = TypedError(
        ErrorCategory.INTERNAL,
        "order_cancellation_database_error",
        "訂單取消交易寫入失敗。",
        correlation_id,
    )
    raise _http_error(500, typed) from error


def _raise_value_error(error, correlation_id):
    code = str(error)
    category = (
        ErrorCategory.NOT_FOUND
        if code in {"order_not_found", "order_cancellation_receipt_not_found"}
        else ErrorCategory.VALIDATION
    )
    status_code = 404 if category is ErrorCategory.NOT_FOUND else 422
    typed = TypedError(
        category,
        code or "order_cancellation_validation_error",
        "訂單取消請求未通過驗證。",
        correlation_id,
    )
    raise _http_error(status_code, typed) from error


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "order_cancellation_internal_error",
            "訂單取消處理失敗。",
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
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return _materialize_collection(value)


def _materialize_collection(value):
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value

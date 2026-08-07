"""Typed Query, Preview, and Apply endpoints for Orders Terms."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, Field
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_terms import (
    OrderTermsApplication,
    get_order_terms_application,
)
from api.schemas.base import BaseResponse
from api.schemas.order_terms import (
    OrderTermsPreviewView,
    OrderTermsQueryView,
    OrderTermsReceiptView,
)
from domains.orders.terms import OrderTerms, ServiceTimeTerms
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
from subsystems.orders.terms_workflow import (
    OrderTermsApplyRequest,
    TermsWorkflowError,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Orders Terms"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class ServiceTimeTermsInput(BaseModel):
    start_time: time
    end_time: time
    end_day_offset: int = Field(ge=0, le=1)


class OrderTermsInput(BaseModel):
    planned_start_date: date
    service_days: int = Field(gt=0)
    service_hours_per_day: int = Field(gt=0)
    floor_fee_ntd: int = Field(ge=0)
    service_time: ServiceTimeTermsInput

    def to_domain(self) -> OrderTerms:
        service_time = self.service_time
        return OrderTerms(
            self.planned_start_date,
            self.service_days,
            self.service_hours_per_day,
            MoneyNTD(self.floor_fee_ntd),
            ServiceTimeTerms(
                service_time.start_time,
                service_time.end_time,
                service_time.end_day_offset,
            ),
        )


class OrderTermsPreviewRequest(BaseModel):
    proposed_terms: OrderTermsInput


class OrderTermsApplyBody(OrderTermsPreviewRequest):
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    expected_client_finance_version: int = Field(ge=0)
    expected_payroll_version: int = Field(ge=0)
    preview_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    reason: str = Field(min_length=1, max_length=500)


@router.get(
    "/{case_no}/terms",
    response_model=BaseResponse[OrderTermsQueryView],
)
def query_order_terms(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderTermsApplication = Depends(get_order_terms_application),
):
    del principal
    return _call_endpoint(
        lambda: _query_payload(application.query(case_no)),
        "成功取得訂單條款",
        CorrelationId(f"query:{case_no}"),
    )


@router.post(
    "/{case_no}/terms/preview",
    response_model=BaseResponse[OrderTermsPreviewView],
)
def preview_order_terms(
    body: OrderTermsPreviewRequest,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "orders-terms-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderTermsApplication = Depends(get_order_terms_application),
):
    del principal
    identity = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _preview_payload(
            application.preview(case_no, body.proposed_terms.to_domain())
        ),
        "成功產生訂單條款變更預覽",
        identity,
    )


@router.post(
    "/{case_no}/terms/apply",
    response_model=BaseResponse[OrderTermsReceiptView],
)
# FastAPI requires the complete HTTP contract on this callable for OpenAPI generation.
def apply_order_terms(
    body: OrderTermsApplyBody,
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
    application: OrderTermsApplication = Depends(get_order_terms_application),
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
        "成功套用訂單條款變更",
        request.correlation_id,
    )


def _apply_request(case_no, body, key, correlation, principal):
    actor_id = str(principal.username or "").strip()
    return OrderTermsApplyRequest(
        case_no,
        body.proposed_terms.to_domain(),
        ExpectedVersion(body.expected_order_version),
        ExpectedVersion(body.expected_scheduling_version),
        ExpectedVersion(body.expected_client_finance_version),
        ExpectedVersion(body.expected_payroll_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(actor_id),
        body.reason,
        CorrelationId(correlation),
    )


def _query_payload(facts) -> dict[str, Any]:
    return {
        "case_no": facts.order.case_no,
        "order_version": facts.order.version,
        "scheduling_version": facts.scheduling.aggregate_version,
        "scheduling_generation": facts.scheduling.generation_number,
        "client_finance_version": facts.client_finance.account_version,
        "payroll_version": facts.payroll.payroll_version,
        "service_data_locked": facts.order.service_data_locked,
        "terms": facts.order.terms.canonical_payload(),
    }


def _preview_payload(preview) -> dict[str, Any]:
    return {
        "before": preview.before.canonical_payload(),
        "after": preview.after.canonical_payload(),
        "order_version": preview.order_version,
        "scheduling_version": preview.scheduling_version,
        "scheduling_generation": preview.scheduling_generation,
        "client_finance_version": preview.client_finance_version,
        "payroll_version": preview.payroll_version,
        "scheduling": _materialize(preview.scheduling),
        "client_finance_impact": _materialize(preview.client_finance_impact),
        "payroll_impact": _materialize(preview.payroll_impact),
        "lifecycle_impact": _materialize(preview.lifecycle_impact),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _call_endpoint(command, message, correlation_id):
    try:
        return _success_response(command, message)
    except TermsWorkflowError as error:
        _raise_typed_error(error.error)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except ValueError as error:
        _raise_value_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


def _success_response(command, message):
    payload = command()
    if not isinstance(payload, dict):
        raise TypeError("Orders Terms endpoint result must be an object")
    return BaseResponse(data=payload, message=message)


def _internal_error(correlation_id):
    error = TypedError(
        ErrorCategory.INTERNAL,
        "orders_terms_internal_error",
        "Orders Terms processing failed.",
        correlation_id,
    )
    return _http_error(500, error)


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


def _raise_mysql_error(error, correlation_id) -> None:
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "orders_terms_transaction_temporarily_unavailable",
            "The transaction can be retried with the same idempotency key.",
            correlation_id,
            retryable=True,
        )
        raise _http_error(503, typed, headers={"Retry-After": "1"}) from error
    typed = TypedError(
        ErrorCategory.INTERNAL,
        "orders_terms_database_error",
        "Orders Terms persistence failed.",
        correlation_id,
    )
    raise _http_error(500, typed) from error


def _raise_value_error(error, correlation_id) -> None:
    code = str(error)
    if code == "order_not_found":
        category, status_code = ErrorCategory.NOT_FOUND, 404
    elif code.endswith("_required") or code == "service_data_locked":
        category, status_code = ErrorCategory.DOMAIN_BLOCKED, 409
    elif "conflict" in code or code == "stale_preview":
        category, status_code = ErrorCategory.CONFLICT, 409
    else:
        category, status_code = ErrorCategory.VALIDATION, 422
    raise _http_error(
        status_code,
        TypedError(category, code, "Orders Terms request was rejected.", correlation_id),
    ) from error


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

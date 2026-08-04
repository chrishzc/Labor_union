"""Typed Query, Preview, and Apply endpoints for Actual Start."""

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
from api.dependencies.order_actual_start import (
    ActualStartApplication,
    get_actual_start_application,
)
from api.schemas.base import BaseResponse
from api.schemas.order_actual_start import (
    ActualStartPreviewView,
    ActualStartQueryView,
    ActualStartReceiptView,
)
from domains.orders.actual_start import ActualStartCandidateError
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.orders.actual_start_workflow import (
    ActualStartApplyRequest,
    ActualStartWorkflowError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["Actual Start"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class ActualStartPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_actual_start_date: date


class ActualStartApplyBody(ActualStartPreviewBody):
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    expected_client_finance_version: int = Field(ge=0)
    expected_payroll_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


@router.get(
    "/{case_no}/actual-start",
    response_model=BaseResponse[ActualStartQueryView],
)
def query_actual_start(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ActualStartApplication = Depends(get_actual_start_application),
):
    del principal
    return _call_endpoint(
        lambda: _query_payload(application.query(case_no)),
        "成功取得實際開工日狀態",
        CorrelationId(f"query:{case_no}"),
    )


@router.post(
    "/{case_no}/actual-start/preview",
    response_model=BaseResponse[ActualStartPreviewView],
)
def preview_actual_start(
    body: ActualStartPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "actual-start-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ActualStartApplication = Depends(get_actual_start_application),
):
    del principal
    identity = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _preview_payload(
            application.preview(case_no, body.new_actual_start_date)
        ),
        "成功產生實際開工日預覽",
        identity,
    )


@router.post(
    "/{case_no}/actual-start/apply",
    response_model=BaseResponse[ActualStartReceiptView],
)
# FastAPI requires the complete HTTP contract on this callable for OpenAPI generation.
def apply_actual_start(
    body: ActualStartApplyBody,
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
    application: ActualStartApplication = Depends(get_actual_start_application),
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
        "成功套用實際開工日",
        request.correlation_id,
    )


def _apply_request(case_no, body, key, correlation, principal):
    actor_id = str(principal.username or "").strip()
    return ActualStartApplyRequest(
        case_no,
        body.new_actual_start_date,
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
        "current_actual_start_date": facts.lifecycle.actual_start_date,
        "planned_start_date": facts.order.terms.planned_start_date,
        "service_data_locked": facts.order.service_data_locked,
        "order_version": facts.order.version,
        "scheduling_version": facts.scheduling.aggregate_version,
        "scheduling_generation": facts.scheduling.generation_number,
        "client_finance_version": facts.client_finance.account_version,
        "payroll_version": facts.payroll.payroll_version,
    }


def _preview_payload(preview) -> dict[str, Any]:
    return {
        "before_actual_start_date": preview.before_actual_start_date,
        "after_actual_start_date": preview.after_actual_start_date,
        "actual_end_date": preview.actual_start.actual_end_date,
        "order_version": preview.order_version,
        "scheduling_version": preview.scheduling_version,
        "scheduling_generation": preview.scheduling_generation,
        "client_finance_version": preview.client_finance_version,
        "payroll_version": preview.payroll_version,
        "actual_start": _materialize(preview.actual_start),
        "scheduling": _materialize(preview.scheduling),
        "client_finance_impact": _materialize(preview.client_finance_impact),
        "payroll_impact": _materialize(preview.payroll_impact),
        "lifecycle_impact": _materialize(preview.lifecycle_impact),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _call_endpoint(command, message, correlation_id):
    try:
        payload = command()
        return BaseResponse(data=payload, message=message)
    except ActualStartWorkflowError as error:
        _raise_typed_error(error.error)
    except ActualStartCandidateError as error:
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
    typed = TypedError(
        ErrorCategory.DOMAIN_BLOCKED,
        error.blocker.value,
        "實際開工日變更需要人員先處理阻擋原因。",
        correlation_id,
        domain_blockers=(error.blocker.value,),
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
            "actual_start_transaction_temporarily_unavailable",
            "可使用相同冪等鍵重試這次交易。",
            correlation_id,
            retryable=True,
        )
        raise _http_error(503, typed, headers={"Retry-After": "1"}) from error
    typed = TypedError(
        ErrorCategory.INTERNAL,
        "actual_start_database_error",
        "實際開工日交易寫入失敗。",
        correlation_id,
    )
    raise _http_error(500, typed) from error


def _raise_value_error(error, correlation_id):
    code = str(error)
    category = ErrorCategory.NOT_FOUND if code == "order_not_found" else ErrorCategory.VALIDATION
    status_code = 404 if category is ErrorCategory.NOT_FOUND else 422
    
    if code == "scheduling_generation_conflict":
        message = "此案件尚未完成正式排班指派，暫無法進行實際開工日確認。"
    elif code == "scheduling_effective_generation_invalid":
        message = "此案件的排班資料無效，無法進行實際開工日確認。"
    else:
        message = "實際開工日請求未通過驗證。"
        
    typed = TypedError(
        category,
        code or "actual_start_validation_error",
        message,
        correlation_id,
    )
    raise _http_error(status_code, typed) from error


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "actual_start_internal_error",
            "實際開工日處理失敗。",
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

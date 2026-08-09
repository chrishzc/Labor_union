"""Typed Query, Preview, and Apply endpoints for contract completion."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_contract_completion import (
    ContractCompletionApplication,
    get_contract_completion_application,
)
from api.schemas.base import BaseResponse
from api.schemas.order_contract_completion import (
    ContractCompletionPreviewView,
    ContractCompletionQueryView,
    ContractCompletionReceiptView,
)
from domains.orders.contract_completion import (
    ContractCompletionCandidateError,
    ContractCompletionIntent,
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
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionApplyRequest,
    ContractCompletionWorkflowError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["Contract Completion"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class ContractCompletionPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: ContractCompletionIntent


class ContractCompletionApplyBody(ContractCompletionPreviewBody):
    expected_order_version: int = Field(ge=0)
    expected_client_finance_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


@router.get(
    "/{case_no}/contract-completion",
    response_model=BaseResponse[ContractCompletionQueryView],
)
def query_contract_completion(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ContractCompletionApplication = Depends(
        get_contract_completion_application
    ),
):
    del principal
    correlation = CorrelationId(f"query:{case_no}")
    return _call_endpoint(
        lambda: _query_payload(application.query(case_no)),
        "成功取得契約完成狀態",
        correlation,
    )


@router.post(
    "/{case_no}/contract-completion/preview",
    response_model=BaseResponse[ContractCompletionPreviewView],
)
def preview_contract_completion(
    body: ContractCompletionPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "contract-completion-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ContractCompletionApplication = Depends(
        get_contract_completion_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _preview_payload(application.preview(case_no, body.intent)),
        "成功產生契約完成預覽",
        correlation,
    )


@router.post(
    "/{case_no}/contract-completion/apply",
    response_model=BaseResponse[ContractCompletionReceiptView],
)
# FastAPI requires the complete HTTP contract here for OpenAPI generation.
def apply_contract_completion(
    body: ContractCompletionApplyBody,
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
    application: ContractCompletionApplication = Depends(
        get_contract_completion_application
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
        "成功記錄契約完成",
        request.correlation_id,
    )


def _apply_request(case_no, body, key, correlation, principal):
    actor_id = str(principal.username or "").strip()
    return ContractCompletionApplyRequest(
        case_no,
        body.intent,
        ExpectedVersion(body.expected_order_version),
        ExpectedVersion(body.expected_client_finance_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(actor_id),
        body.reason,
        CorrelationId(correlation),
    )


def _query_payload(query):
    facts = query.facts
    return {
        "case_no": facts.case_no,
        "order_version": facts.aggregate_version,
        "client_finance_version": query.client_finance_version,
        "contract_identity": facts.contract_identity,
        "contract_completed": facts.contract_completed,
        "lifecycle_status": facts.lifecycle_status.value,
        "deposit_settled": facts.deposit_settled,
        "service_time_terms_complete": facts.service_time.complete,
        "completion_available": query.completion_available,
        "domain_blockers": [
            blocker.value for blocker in query.domain_blockers
        ],
    }


def _preview_payload(preview):
    candidate = preview.candidate
    return {
        "intent": candidate.intent.value,
        "contract_identity": candidate.contract_identity,
        "order_version": candidate.expected_order_version,
        "resulting_order_version": candidate.resulting_order_version,
        "client_finance_version": (
            preview.client_finance_impact.expected_account_version
        ),
        "client_finance_impact": _client_finance_impact_payload(
            preview.client_finance_impact
        ),
        "before_completed": candidate.before_completed,
        "after_completed": candidate.after_completed,
        "before_status": candidate.before_status.value,
        "after_status": candidate.after_status.value,
        "deposit_settled": candidate.deposit_settled,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _client_finance_impact_payload(impact):
    return {
        "expected_account_version": impact.expected_account_version,
        "resulting_account_version": impact.resulting_account_version,
        "established_obligation_count": sum(
            action.action.value == "create_stage"
            for action in impact.actions
        ),
        "stage_plans": [
            _stage_plan_payload(stage_plan)
            for stage_plan in impact.stage_plans
        ],
    }


def _stage_plan_payload(stage_plan):
    return {
        "payment_stage": stage_plan.payment_stage.value,
        "service_day_count": len(stage_plan.service_dates),
        "amount_ntd": stage_plan.amount.amount,
        "due_date": stage_plan.due_date,
    }


def _call_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except ContractCompletionWorkflowError as error:
        _raise_typed_error(error.error)
    except ContractCompletionCandidateError as error:
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
    blockers = tuple(blocker.value for blocker in error.blockers)
    typed = TypedError(
        ErrorCategory.DOMAIN_BLOCKED,
        "contract_completion_blocked",
        "契約完成前仍有根事實需要人員處理。",
        correlation_id,
        domain_blockers=blockers,
    )
    raise _http_error(409, typed) from error


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
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "contract_completion_temporarily_unavailable",
            "可使用相同冪等鍵重試這次交易。",
            correlation_id,
            retryable=True,
        )
        raise _http_error(503, typed, headers={"Retry-After": "1"}) from error
    typed = TypedError(
        ErrorCategory.INTERNAL,
        "contract_completion_database_error",
        "契約完成交易寫入失敗。",
        correlation_id,
    )
    raise _http_error(500, typed) from error


def _raise_value_error(error, correlation_id):
    code = str(error)
    not_found = code == "order_not_found"
    typed = TypedError(
        ErrorCategory.NOT_FOUND if not_found else ErrorCategory.VALIDATION,
        code or "contract_completion_validation_error",
        "契約完成請求未通過驗證。",
        correlation_id,
    )
    raise _http_error(404 if not_found else 422, typed) from error


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "contract_completion_internal_error",
            "契約完成處理失敗。",
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
    return _materialize_collection(value)


def _materialize_collection(value):
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value


__all__ = [
    "ContractCompletionApplyBody",
    "ContractCompletionPreviewBody",
    "router",
]

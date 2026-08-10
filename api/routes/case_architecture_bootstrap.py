"""Typed Preview and Apply endpoints for first-use case bootstrap."""

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.case_architecture_bootstrap import (
    get_case_architecture_bootstrap_status_service,
    get_case_architecture_bootstrap_workflow,
)
from api.schemas.base import BaseResponse
from api.schemas.case_architecture_bootstrap import (
    CaseArchitectureBootstrapApplyBody,
    CaseArchitectureBootstrapIntentBody,
    CaseArchitectureBootstrapPreviewView,
    CaseArchitectureBootstrapReceiptView,
    CaseArchitectureBootstrapStatusView,
)
from domains.bootstrap.case_architecture import (
    CaseArchitectureBootstrapIntent,
    ClientPaymentTermsRootFacts,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.bootstrap.case_architecture_status import (
    CaseArchitectureBootstrapStatusService,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.bootstrap.case_architecture_workflow import (
    CaseArchitectureBootstrapWorkflow,
    CaseArchitectureBootstrapWorkflowError,
    EnsureCaseArchitectureBootstrap,
)

router = APIRouter(prefix="/api/v1/cases", tags=["Case Bootstrap"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


@router.get(
    "/{case_no}/architecture-bootstrap/status",
    response_model=BaseResponse[CaseArchitectureBootstrapStatusView],
)
def query_case_architecture_bootstrap_status(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    service: CaseArchitectureBootstrapStatusService = Depends(
        get_case_architecture_bootstrap_status_service
    ),
):
    del principal
    try:
        status = service.query(case_no)
        return BaseResponse(
            data=_status_payload(status),
            message="成功讀取案件架構狀態",
        )
    except ValueError as error:
        raise _http_error(
            404 if str(error) == "case_not_found" else 422,
            TypedError(
                ErrorCategory.NOT_FOUND
                if str(error) == "case_not_found"
                else ErrorCategory.VALIDATION,
                str(error),
                "找不到案件。" if str(error) == "case_not_found" else str(error),
                CorrelationId("case-bootstrap-status"),
            ),
        ) from error


@router.post(
    "/{case_no}/architecture-bootstrap/preview",
    response_model=BaseResponse[CaseArchitectureBootstrapPreviewView],
)
def preview_case_architecture_bootstrap(
    body: CaseArchitectureBootstrapIntentBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "case-bootstrap-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow: CaseArchitectureBootstrapWorkflow = Depends(
        get_case_architecture_bootstrap_workflow
    ),
):
    del principal
    identity = CorrelationId(correlation_id)
    intent = _intent(case_no, body)
    return _call(
        lambda: _preview_payload(workflow.preview(intent, identity)),
        "成功產生案件初始架構預覽",
        identity,
    )


@router.post(
    "/{case_no}/architecture-bootstrap/apply",
    response_model=BaseResponse[CaseArchitectureBootstrapReceiptView],
)
# FastAPI requires the full HTTP contract on this application boundary.
def apply_case_architecture_bootstrap(
    body: CaseArchitectureBootstrapApplyBody,
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
    workflow: CaseArchitectureBootstrapWorkflow = Depends(
        get_case_architecture_bootstrap_workflow
    ),
):
    command = _command(
        case_no,
        body,
        idempotency_key,
        correlation_id,
        principal,
    )
    return _call(
        lambda: _receipt_payload(workflow.ensure(command)),
        "成功建立案件初始架構",
        command.correlation_id,
    )


def _intent(case_no, body):
    return CaseArchitectureBootstrapIntent(
        case_no=case_no,
        client_payment_terms=ClientPaymentTermsRootFacts(
            policy_version=body.client_payment_policy_version,
            client_hourly_rate=MoneyNTD(body.client_hourly_rate_ntd),
            deposit_service_days=body.deposit_service_days,
            deposit_due_date=body.deposit_due_date,
            first_payment_due_date=body.first_payment_due_date,
        ),
        payroll_policy_version=body.payroll_policy_version,
    )


def _command(case_no, body, key, correlation, principal):
    return EnsureCaseArchitectureBootstrap(
        intent=_intent(case_no, body),
        expected_order_version=ExpectedVersion(body.expected_order_version),
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
        idempotency_key=IdempotencyKey(key),
        actor=ActorContext(str(principal.username or "").strip()),
        reason=body.reason,
        correlation_id=CorrelationId(correlation),
    )


def _preview_payload(preview):
    candidate = preview.candidate
    terms = candidate.client_payment_terms
    policy = candidate.payroll_rate_policy
    return {
        "case_no": candidate.case_no,
        "order_version": candidate.order_version,
        "source_identity_status": candidate.source_identity_status,
        "client_payment_policy_version": terms.policy_version,
        "client_hourly_rate_ntd": terms.client_hourly_rate.amount,
        "deposit_service_days": terms.deposit_service_days,
        "deposit_due_date": terms.deposit_due_date,
        "first_payment_due_date": terms.first_payment_due_date,
        "payroll_policy_version": policy.policy_version,
        "payroll_policy_kind": policy.policy_kind.value,
        "payroll_hourly_rate_ntd": policy.hourly_rate.amount,
        "scheduling_version": getattr(candidate, "scheduling_version", 0),
        "scheduling_generation": candidate.scheduling_generation,
        "mutation": candidate.mutation.value,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "order_version": receipt.order_version,
        "client_finance_version": receipt.client_finance_version,
        "payroll_version": receipt.payroll_version,
        "scheduling_version": receipt.scheduling_version,
        "scheduling_generation": receipt.scheduling_generation,
        "bootstrap_created": receipt.bootstrap_created,
        "bootstrap_event_id": receipt.bootstrap_event_id,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _status_payload(status):
    recommendation = status.recommendation
    return {
        "case_no": status.case_no,
        "ready": status.ready,
        "scheduling_version": status.scheduling_version,
        "scheduling_generation": status.scheduling_generation,
        "service_time_complete": status.service_time_complete,
        "recommendation": (
            _intent_payload(recommendation) if recommendation else None
        ),
        "domain_blockers": list(status.domain_blockers),
    }


def _intent_payload(intent):
    terms = intent.client_payment_terms
    return {
        "client_payment_policy_version": terms.policy_version,
        "client_hourly_rate_ntd": terms.client_hourly_rate.amount,
        "deposit_service_days": terms.deposit_service_days,
        "deposit_due_date": terms.deposit_due_date,
        "first_payment_due_date": terms.first_payment_due_date,
        "payroll_policy_version": intent.payroll_policy_version,
    }


def _call(
    command: Callable[[], dict[str, object]],
    message: str,
    correlation_id: CorrelationId,
):
    try:
        return BaseResponse(data=command(), message=message)
    except CaseArchitectureBootstrapWorkflowError as error:
        _raise_typed(error.error)
    except OperationalError as error:
        _raise_mysql(error, correlation_id)
    except (TypeError, ValueError) as error:
        raise _http_error(
            422,
            TypedError(
                ErrorCategory.VALIDATION,
                "invalid_case_architecture_bootstrap_request",
                str(error),
                correlation_id,
            ),
        ) from error
    except HTTPException:
        raise
    except Exception as error:
        raise _http_error(
            500,
            TypedError(
                ErrorCategory.INTERNAL,
                "transaction_failed",
                "案件初始架構交易失敗並已回滾。",
                correlation_id,
            ),
        ) from error


def _raise_typed(error: TypedError):
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
    raise _http_error(status, error)


def _raise_mysql(error, correlation_id):
    code = int(error.args[0]) if error.args else 0
    retryable = code in _RETRYABLE_MYSQL_CODES
    typed = TypedError(
        ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
        "transaction_retryable" if retryable else "transaction_failed",
        "資料庫暫時忙碌，請使用相同冪等鍵重試。"
        if retryable
        else "案件初始架構交易失敗並已回滾。",
        correlation_id,
        retryable=retryable,
    )
    raise _http_error(503 if retryable else 500, typed) from error


def _http_error(status_code, error):
    detail = {
        "error": {
            "category": error.category.value,
            "code": error.code,
            "message": error.message,
            "correlation_id": error.correlation_id.value,
            "domain_blockers": list(error.domain_blockers),
            "retryable": error.retryable,
            "current_version": (
                error.current_version.value
                if error.current_version is not None
                else None
            ),
        }
    }
    headers = {"Retry-After": "1"} if error.retryable else None
    return HTTPException(status_code=status_code, detail=detail, headers=headers)


__all__ = ["router"]

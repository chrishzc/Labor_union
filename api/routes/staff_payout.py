"""Authenticated typed HTTP endpoints for Staff Payout Reconciliation."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.staff_payout import (
    StaffPayoutApplication,
    get_staff_payout_application,
)
from api.schemas.base import BaseResponse
from api.schemas.jobs import JobAcceptedResponse
from api.dependencies.jobs import get_job_repository
from infrastructure.mysql.background_job_repository import (
    BackgroundJobRepository,
    JobIdempotencyConflict,
)
from shared_kernel.durable_job_queue import DurableJobCommand
from api.schemas.staff_payout import (
    PayoutApplyBody,
    PayoutPreviewBody,
    ReturnApplyBody,
    ReturnPreviewBody,
    ReversalApplyBody,
    ReversalPreviewBody,
    StaffPayablesQueryView,
    StaffPayoutPreviewView,
    StaffPayoutReceiptView,
)
from domains.staff_payables.reconciliation import StaffPayoutEventType
from infrastructure.mysql.staff_payout_repository import (
    build_return_reopen_identity,
    build_reversal_reopen_identity,
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
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutReconciliationError,
    StaffPayoutSelection,
)

router = APIRouter(prefix="/api/v1/staff-payables", tags=["Staff Payables"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


@router.post(
    "/payout/preview",
    response_model=BaseResponse[StaffPayoutPreviewView],
)
def preview_payout(
    body: PayoutPreviewBody,
    correlation_id: _CorrelationHeader = "staff-payout-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffPayoutApplication = Depends(get_staff_payout_application),
):
    del principal
    return _preview_response(
        application,
        lambda: _payout_selection(body),
        CorrelationId(correlation_id),
    )


@router.post(
    "/payout/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_payout(
    body: PayoutApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    return _apply_response(
        lambda: _apply_request(
            _payout_selection(body),
            body,
            idempotency_key,
            correlation_id,
            principal,
        ),
        job_repository,
    )


@router.post(
    "/return/preview",
    response_model=BaseResponse[StaffPayoutPreviewView],
)
def preview_return(
    body: ReturnPreviewBody,
    correlation_id: _CorrelationHeader = "staff-return-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffPayoutApplication = Depends(get_staff_payout_application),
):
    del principal
    return _preview_response(
        application,
        lambda: _return_selection(body),
        CorrelationId(correlation_id),
    )


@router.post(
    "/return/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_return(
    body: ReturnApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    return _apply_response(
        lambda: _apply_request(
            _return_selection(body),
            body,
            idempotency_key,
            correlation_id,
            principal,
        ),
        job_repository,
    )


@router.post(
    "/reversal/preview",
    response_model=BaseResponse[StaffPayoutPreviewView],
)
def preview_reversal(
    body: ReversalPreviewBody,
    correlation_id: _CorrelationHeader = "staff-reversal-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffPayoutApplication = Depends(get_staff_payout_application),
):
    del principal
    return _preview_response(
        application,
        lambda: _reversal_selection(body),
        CorrelationId(correlation_id),
    )


@router.post(
    "/reversal/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_reversal(
    body: ReversalApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    return _apply_response(
        lambda: _apply_request(
            _reversal_selection(body),
            body,
            idempotency_key,
            correlation_id,
            principal,
        ),
        job_repository,
    )


@router.get(
    "/{staff_id}",
    response_model=BaseResponse[StaffPayablesQueryView],
)
def query_staff_payables(
    staff_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffPayoutApplication = Depends(get_staff_payout_application),
):
    del principal
    return _call_endpoint(
        lambda: application.query(staff_id),
        "成功取得月嫂應付款與付款事件",
        CorrelationId(f"staff-payables-query:{staff_id}"),
    )


def _preview_response(application, build_selection, correlation_id):
    return _call_endpoint(
        lambda: _build_preview_payload(
            application,
            build_selection,
            correlation_id,
        ),
        "成功產生月嫂付款核銷預覽",
        correlation_id,
    )


def _build_preview_payload(application, build_selection, correlation_id):
    selection = build_selection()
    preview = application.preview(selection, correlation_id)
    return _preview_payload(preview, selection.event_type)


def _apply_response(build_request, job_repository):
    request = build_request()
    job_id = str(uuid.uuid4())
    try:
        job_id = job_repository.enqueue_command(
            _staff_payout_command(job_id, request)
        )
    except JobIdempotencyConflict as e:
        job_id = e.job_id

    return BaseResponse(
        data=JobAcceptedResponse(job_id=job_id, status_url=f"/api/v1/jobs/{job_id}"),
        message="202 Accepted",
    )


def _staff_payout_command(job_id, request):
    return DurableJobCommand(
        job_id,
        request.idempotency_key.value,
        "staff_payout_apply",
        1,
        _staff_payout_payload(request),
        request.actor.actor_id,
        request.correlation_id.value,
    )


def _staff_payout_payload(request):
    selection = request.selection
    return {
        "actor": request.actor.actor_id,
        "correlation_id": request.correlation_id.value,
        "expected_bank_facts_version": request.expected_bank_facts_version.value,
        "expected_staff_payables_version": request.expected_staff_payables_version.value,
        "idempotency_key": request.idempotency_key.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "reason": request.reason,
        "selection": {
            "event_type": selection.event_type.value,
            "bank_fact_identities": list(selection.bank_fact_identities),
            "obligation_identities": list(selection.obligation_identities),
            "reopen_fact_identity": selection.reopen_fact_identity,
        },
    }


def _payout_selection(body) -> StaffPayoutSelection:
    return StaffPayoutSelection(
        StaffPayoutEventType.PAYOUT,
        _canonical_integer_identities(body.finance_import_row_ids),
        _canonical_text_identities(body.obligation_identities),
    )


def _return_selection(body) -> StaffPayoutSelection:
    identity = build_return_reopen_identity(
        body.return_finance_import_row_id,
        body.source_payout_event_id,
    )
    return StaffPayoutSelection(
        StaffPayoutEventType.RETURN,
        (),
        _canonical_text_identities(body.obligation_identities),
        identity,
    )


def _reversal_selection(body) -> StaffPayoutSelection:
    identity = build_reversal_reopen_identity(
        body.source_payout_event_id,
        body.occurred_on,
    )
    return StaffPayoutSelection(
        StaffPayoutEventType.REVERSAL,
        (),
        _canonical_text_identities(body.obligation_identities),
        identity,
    )


def _apply_request(selection, body, key, correlation, principal):
    actor_id = str(principal.username or "").strip()
    return StaffPayoutApplyRequest(
        selection,
        ExpectedVersion(body.expected_staff_payables_version),
        ExpectedVersion(body.expected_bank_facts_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(actor_id),
        body.reason,
        CorrelationId(correlation),
    )


def _preview_payload(preview, event_type):
    return {
        "event_type": event_type.value,
        "staff_payables_version": preview.staff_payables_version,
        "bank_facts_version": preview.bank_facts_version,
        "candidate": _materialize(preview.candidate),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _canonical_integer_identities(values) -> tuple[str, ...]:
    identities = tuple(str(value) for value in values)
    _reject_duplicates(identities)
    return tuple(sorted(identities, key=int))


def _canonical_text_identities(values) -> tuple[str, ...]:
    identities = tuple(value.strip() for value in values)
    if any(not value for value in identities):
        raise ValueError("invalid_staff_payout_intent")
    _reject_duplicates(identities)
    return tuple(sorted(identities))


def _reject_duplicates(identities) -> None:
    if len(identities) != len(set(identities)):
        raise ValueError("invalid_staff_payout_intent")


def _call_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except StaffPayoutReconciliationError as error:
        _raise_typed_error(error.error)
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


def _raise_mysql_error(error, correlation_id):
    mysql_code = int(error.args[0]) if error.args else 0
    retryable = mysql_code in _RETRYABLE_MYSQL_CODES
    category = ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL
    status_code = 503 if retryable else 500
    typed = TypedError(
        category,
        "transaction_failed",
        "月嫂付款交易暫時無法完成。" if retryable else "月嫂付款資料庫交易失敗。",
        correlation_id,
        retryable=retryable,
    )
    headers = {"Retry-After": "1"} if retryable else None
    raise _http_error(status_code, typed, headers=headers) from error


def _raise_value_error(error, correlation_id):
    code = str(error) or "invalid_staff_payout_intent"
    typed = TypedError(
        ErrorCategory.VALIDATION,
        code,
        "月嫂付款核銷請求未通過驗證。",
        correlation_id,
    )
    raise _http_error(422, typed) from error


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "transaction_failed",
            "月嫂付款核銷交易失敗。",
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


__all__ = ["router"]

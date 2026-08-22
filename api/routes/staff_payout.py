"""
File: staff_payout.py
Description: 提供 Staff Payables typed Query／Preview，並以 Durable Job Bridge 接受付款命令。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_admin, require_capability, require_system_admin
from api.dependencies.staff_payout import (
    StaffPayoutApplication,
    get_staff_overpayment_recovery_application,
    get_staff_overpayment_recovery_matching_application,
    get_staff_payout_application,
)
from api.schemas.base import BaseResponse
from api.schemas.jobs import JobAcceptedResponse
from api.dependencies.jobs import (
    durable_job_conflict_http_error,
    get_durable_job_application,
    immutable_admin_job_actor,
)
from shared_kernel.durable_job_queue import DurableJobCommand
from subsystems.jobs.command_application import DurableJobCommandApplication
from subsystems.jobs.contracts import DurableJobCommandConflict
from api.schemas.staff_payout import (
    PayoutApplyBody,
    PayoutDifferenceApplyBody,
    PayoutDifferencePreviewBody,
    PayoutPreviewBody,
    ReturnApplyBody,
    ReturnPreviewBody,
    ReversalApplyBody,
    ReversalPreviewBody,
    StaffPayablesQueryView,
    StaffPayoutPreviewView,
    StaffPayoutDifferenceSourceView,
    StaffPayoutReceiptView,
    StaffOverpaymentRecoveryApplyBody,
    StaffOverpaymentRecoveryMatchedApplyBody,
    StaffOverpaymentRecoveryMatchedPreviewBody,
    StaffOverpaymentRecoveryMatchingApplyBody,
    StaffOverpaymentRecoveryMatchingPreviewBody,
    StaffOverpaymentRecoveryMatchingPreviewView,
    StaffOverpaymentRecoveryMatchingReceiptView,
    StaffOverpaymentRecoveryAdjustmentApplyBody,
    StaffOverpaymentRecoveryAdjustmentPreviewBody,
    StaffOverpaymentRecoveryAdjustmentPreviewView,
    StaffOverpaymentRecoveryPreviewBody,
    StaffOverpaymentRecoveryPreviewView,
    StaffOverpaymentRecoveryReceiptView,
)
from domains.staff_payables.reconciliation import StaffPayoutDifferenceMode, StaffPayoutEventType
from infrastructure.mysql.staff_payout_repository import (
    build_return_reopen_identity,
    build_reversal_reopen_identity,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
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
from subsystems.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecoveryAction,
    StaffOverpaymentRecoveryApplyRequest,
    StaffOverpaymentRecoveryError,
    StaffOverpaymentRecoverySelection,
    StaffOverpaymentRecoveryWorkflow,
)
from subsystems.staff_payables.overpayment_recovery_matching import (
    StaffOverpaymentRecoveryMatchingApplyRequest,
    StaffOverpaymentRecoveryMatchingError,
    StaffOverpaymentRecoveryMatchingSelection,
    StaffOverpaymentRecoveryMatchingWorkflow,
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
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    return _apply_response(
        lambda: _apply_request(
            _payout_selection(body),
            body,
            idempotency_key,
            correlation_id,
            principal,
        ),
        job_application,
    )


@router.post(
    "/payout-difference/preview",
    response_model=BaseResponse[StaffPayoutPreviewView],
)
def preview_payout_difference(
    body: PayoutDifferencePreviewBody,
    correlation_id: _CorrelationHeader = "staff-payout-difference-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffPayoutApplication = Depends(get_staff_payout_application),
):
    del principal
    return _preview_response(
        application,
        lambda: _payout_difference_selection(body),
        CorrelationId(correlation_id),
    )


@router.post(
    "/payout-difference/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_payout_difference(
    body: PayoutDifferenceApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    return _apply_response(
        lambda: _apply_request(
            _payout_difference_selection(body), body, idempotency_key,
            correlation_id, principal,
        ),
        job_application,
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
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    return _apply_response(
        lambda: _apply_request(
            _return_selection(body),
            body,
            idempotency_key,
            correlation_id,
            principal,
        ),
        job_application,
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
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    return _apply_response(
        lambda: _apply_request(
            _reversal_selection(body),
            body,
            idempotency_key,
            correlation_id,
            principal,
        ),
        job_application,
    )


@router.get(
    "/{staff_id}",
    response_model=BaseResponse[StaffPayablesQueryView],
)
def query_staff_payables(
    staff_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffPayoutApplication = Depends(get_staff_payout_application),
):
    del principal
    return _call_endpoint(
        lambda: application.query(staff_id),
        "成功取得月嫂應付款與付款事件",
        CorrelationId(f"staff-payables-query:{staff_id}"),
    )


@router.get("/payout-differences/{payout_difference_identity}", response_model=BaseResponse[StaffPayoutDifferenceSourceView])
def query_payout_difference_source(
    payout_difference_identity: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffPayoutApplication = Depends(get_staff_payout_application),
):
    del principal
    return _call_endpoint(lambda: application.query_payout_difference_source(payout_difference_identity), "成功取得月嫂付款差額來源", CorrelationId(f"staff-payout-difference-source:{payout_difference_identity}"))


@router.post(
    "/overpayment-recoveries/collection/preview",
    response_model=BaseResponse[StaffOverpaymentRecoveryPreviewView],
)
def preview_overpayment_recovery_collection(
):
    _raise_unmatched_recovery_retired()


@router.post(
    "/overpayment-recoveries/collection/apply",
    response_model=BaseResponse[StaffOverpaymentRecoveryReceiptView],
)
def apply_overpayment_recovery_collection(
):
    _raise_unmatched_recovery_retired()


@router.post("/overpayment-recoveries/matched/preview", response_model=BaseResponse[StaffOverpaymentRecoveryPreviewView])
def preview_matched_overpayment_recovery_collection(
    body: StaffOverpaymentRecoveryMatchedPreviewBody,
    correlation_id: _CorrelationHeader = "staff-overpayment-recovery-matched-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow: StaffOverpaymentRecoveryWorkflow = Depends(get_staff_overpayment_recovery_application),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(lambda: _recovery_preview_payload(workflow.preview(_matched_recovery_selection(body), correlation)), "成功產生已配對月嫂追償收款預覽", correlation)


@router.post("/overpayment-recoveries/matched/apply", response_model=BaseResponse[StaffOverpaymentRecoveryReceiptView])
def apply_matched_overpayment_recovery_collection(
    body: StaffOverpaymentRecoveryMatchedApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow: StaffOverpaymentRecoveryWorkflow = Depends(get_staff_overpayment_recovery_application),
):
    correlation = CorrelationId(correlation_id)
    request = StaffOverpaymentRecoveryApplyRequest(
        _matched_recovery_selection(body), ExpectedVersion(body.expected_recovery_version),
        ExpectedVersion(body.expected_staff_payables_version), PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key), ActorContext(str(principal.username or "").strip()), body.reason, correlation,
    )
    return _call_endpoint(lambda: _materialize(workflow.apply(request)), "已核銷已配對月嫂追償入款", correlation)


@router.post("/overpayment-recoveries/matching/preview", response_model=BaseResponse[StaffOverpaymentRecoveryMatchingPreviewView])
def preview_overpayment_recovery_matching(
    body: StaffOverpaymentRecoveryMatchingPreviewBody,
    correlation_id: _CorrelationHeader = "staff-overpayment-recovery-matching-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow: StaffOverpaymentRecoveryMatchingWorkflow = Depends(get_staff_overpayment_recovery_matching_application),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(lambda: _matching_preview_payload(workflow.preview(_matching_selection(body), correlation)), "成功產生月嫂追償入款配對預覽", correlation)


@router.post("/overpayment-recoveries/matching/apply", response_model=BaseResponse[StaffOverpaymentRecoveryMatchingReceiptView])
def apply_overpayment_recovery_matching(
    body: StaffOverpaymentRecoveryMatchingApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow: StaffOverpaymentRecoveryMatchingWorkflow = Depends(get_staff_overpayment_recovery_matching_application),
):
    correlation = CorrelationId(correlation_id)
    request = StaffOverpaymentRecoveryMatchingApplyRequest(
        _matching_selection(body), ExpectedVersion(body.expected_recovery_version),
        ExpectedVersion(body.expected_staff_payables_version), PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key), ActorContext(str(principal.username or "").strip()),
        body.reason, correlation,
    )
    return _call_matching_endpoint(lambda: _materialize(workflow.apply(request)), "已建立月嫂追償入款配對", correlation)


@router.post(
    "/overpayment-recoveries/adjustment/preview",
    response_model=BaseResponse[StaffOverpaymentRecoveryAdjustmentPreviewView],
)
def preview_overpayment_recovery_adjustment(
    body: StaffOverpaymentRecoveryAdjustmentPreviewBody,
    correlation_id: _CorrelationHeader = "staff-overpayment-recovery-adjustment-preview",
    principal: AdminPrincipal = Depends(
        require_capability("staff_payables.recovery.adjust")
    ),
    workflow: StaffOverpaymentRecoveryWorkflow = Depends(
        get_staff_overpayment_recovery_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _recovery_adjustment_preview_payload(
            workflow.preview(_recovery_adjustment_selection(body), correlation)
        ),
        "成功產生月嫂超額付款追償調整預覽",
        correlation,
    )


@router.post(
    "/overpayment-recoveries/adjustment/apply",
    response_model=BaseResponse[StaffOverpaymentRecoveryReceiptView],
)
def apply_overpayment_recovery_adjustment(
    body: StaffOverpaymentRecoveryAdjustmentApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(
        require_capability("staff_payables.recovery.adjust")
    ),
    workflow: StaffOverpaymentRecoveryWorkflow = Depends(
        get_staff_overpayment_recovery_application
    ),
):
    correlation = CorrelationId(correlation_id)
    request = StaffOverpaymentRecoveryApplyRequest(
        _recovery_adjustment_selection(body),
        ExpectedVersion(body.expected_recovery_version),
        ExpectedVersion(body.expected_staff_payables_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        body.reason,
        correlation,
    )
    return _call_endpoint(
        lambda: _materialize(workflow.apply(request)),
        "已套用月嫂超額付款追償調整",
        correlation,
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


def _apply_response(build_request, job_application):
    request = build_request()
    try:
        acceptance = job_application.enqueue(
            _staff_payout_command(str(uuid.uuid4()), request)
        )
    except DurableJobCommandConflict as error:
        raise durable_job_conflict_http_error(
            error,
            request.correlation_id.value,
        ) from error

    return BaseResponse(
        data=JobAcceptedResponse(
            job_id=acceptance.job_id,
            status_url=f"/api/v1/jobs/{acceptance.job_id}",
        ),
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
            "difference_mode": None if selection.difference_mode is None else selection.difference_mode.value,
        },
    }


def _payout_selection(body) -> StaffPayoutSelection:
    return StaffPayoutSelection(
        StaffPayoutEventType.PAYOUT,
        _canonical_integer_identities(body.finance_import_row_ids),
        _canonical_text_identities(body.obligation_identities),
    )


def _payout_difference_selection(body) -> StaffPayoutSelection:
    return StaffPayoutSelection(
        StaffPayoutEventType.PAYOUT,
        _canonical_integer_identities(body.finance_import_row_ids),
        _canonical_text_identities(body.obligation_identities),
        difference_mode=StaffPayoutDifferenceMode(body.mode),
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
    actor_id = immutable_admin_job_actor(principal, correlation)
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


def _matched_recovery_selection(body) -> StaffOverpaymentRecoverySelection:
    return StaffOverpaymentRecoverySelection(body.recovery_identity.strip(), StaffOverpaymentRecoveryAction.COLLECT, str(body.finance_import_row_id), matching_identity=body.matching_identity.strip(), matching_version=body.matching_version)


def _raise_unmatched_recovery_retired() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "error": {
                "code": "staff_overpayment_recovery_matching_required",
                "message": "追償收款必須先建立不可變入款配對。",
                "replacement": "/overpayment-recoveries/matching/preview",
            }
        },
    )


def _recovery_adjustment_selection(body) -> StaffOverpaymentRecoverySelection:
    return StaffOverpaymentRecoverySelection(
        body.recovery_identity.strip(),
        StaffOverpaymentRecoveryAction.ADJUST,
        adjustment_amount=MoneyNTD(body.adjustment_amount_ntd),
    )


def _matching_selection(body) -> StaffOverpaymentRecoveryMatchingSelection:
    return StaffOverpaymentRecoveryMatchingSelection(body.recovery_identity.strip(), str(body.finance_import_row_id))


def _matching_preview_payload(preview):
    candidate = preview.candidate
    return {"recovery_identity": candidate.recovery_identity, "staff_id": candidate.staff_id, "finance_import_row_identity": candidate.finance_import_row_identity, "recovery_version": candidate.recovery_version, "staff_payables_version": candidate.staff_payables_version, "preview_fingerprint": preview.fingerprint.value}


def _recovery_preview_payload(preview):
    candidate = preview.candidate
    return {
        "recovery_identity": candidate.recovery_identity,
        "recovery_version": preview.recovery_version,
        "staff_payables_version": preview.staff_payables_version,
        "received_amount_ntd": candidate.received_amount.amount,
        "remaining_before_ntd": candidate.remaining_before.amount,
        "remaining_after_ntd": candidate.remaining_after.amount,
        "resulting_status": candidate.resulting_status.value,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _recovery_adjustment_preview_payload(preview):
    candidate = preview.candidate
    return {
        "recovery_identity": candidate.recovery_identity,
        "recovery_version": preview.recovery_version,
        "staff_payables_version": preview.staff_payables_version,
        "adjustment_amount_ntd": candidate.adjustment_amount.amount,
        "remaining_before_ntd": candidate.remaining_before.amount,
        "remaining_after_ntd": candidate.remaining_after.amount,
        "resulting_status": candidate.resulting_status.value,
        "preview_fingerprint": preview.fingerprint.value,
    }


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
    except StaffOverpaymentRecoveryError as error:
        _raise_typed_error(error.error)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except ValueError as error:
        _raise_value_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


def _call_matching_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except StaffOverpaymentRecoveryMatchingError as error:
        _raise_typed_error(error.error)
    except ValueError as error:
        _raise_value_error(error, correlation_id)


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

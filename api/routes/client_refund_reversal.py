"""Authenticated typed endpoints for Client Refund and Client Reversal."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status

from api.dependencies.admin_auth import require_capability, require_system_admin
from api.dependencies.client_refund_reversal import (
    ClientRefundReversalApplication,
    get_client_refund_reversal_application,
)
from api.dependencies.client_over_refund_recovery import (
    ClientOverRefundRecoveryApplication,
    get_client_over_refund_recovery_application,
)
from api.schemas.base import BaseResponse
from api.schemas.client_refund_reversal import (
    ClientRefundApplyBody,
    ClientRefundPreviewBody,
    ClientRefundReversalPreviewView,
    ClientRefundReversalQueryView,
    ClientRefundReversalReceiptView,
    ClientRefundReturnApplyBody,
    ClientRefundReturnPreviewBody,
    ClientOverRefundRecoveryApplyBody,
    ClientOverRefundRecoveryMatchedApplyBody,
    ClientOverRefundRecoveryMatchedPreviewBody,
    ClientOverRefundRecoveryAdjustmentApplyBody,
    ClientOverRefundRecoveryAdjustmentPreviewBody,
    ClientOverRefundRecoveryAdjustmentPreviewView,
    ClientOverRefundRecoveryMatchingApplyBody,
    ClientOverRefundRecoveryMatchingPreviewBody,
    ClientOverRefundRecoveryMatchingPreviewView,
    ClientOverRefundRecoveryMatchingReceiptView,
    ClientOverRefundRecoveryPreviewBody,
    ClientOverRefundRecoveryPreviewView,
    ClientOverRefundRecoveryReceiptView,
    ClientReversalApplyBody,
    ClientReversalPreviewBody,
)
from subsystems.client_finance.over_refund_recovery_workflow import (
    ClientOverRefundRecoveryApplyRequest,
    ClientOverRefundRecoveryError,
    ClientOverRefundRecoverySelection,
    ClientOverRefundRecoveryAction,
)
from subsystems.client_finance.over_refund_recovery_matching_workflow import (
    ClientOverRefundRecoveryMatchingApplyRequest,
    ClientOverRefundRecoveryMatchingError,
    ClientOverRefundRecoveryMatchingSelection,
)
from shared_kernel.money import MoneyNTD
from domains.client_finance.error_contract import (
    canonicalize_client_finance_error,
)
from domains.client_finance.client_refund_reversal import (
    ClientFinanceCorrectionType,
    ClientRefundPurpose,
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
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalApplyRequest,
    ClientRefundReversalError,
    ClientRefundReversalSelection,
)

router = APIRouter(
    prefix="/api/v1/orders/{case_no}/client-finance",
    tags=["Client Finance"],
)
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


@router.get(
    "/refund-reversal",
    response_model=BaseResponse[ClientRefundReversalQueryView],
)
def query_refund_reversal(
    case_no: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(f"client-refund-reversal-query:{case_no}")
    return _call(lambda: application.query(case_no), "成功取得退款與沖正根事實", correlation)


@router.post(
    "/refund/preview",
    response_model=BaseResponse[ClientRefundReversalPreviewView],
)
def preview_refund(
    body: ClientRefundPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-refund-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_refund_selection(case_no, body), correlation)
        ),
        "成功產生客戶退款預覽",
        correlation,
    )


@router.post(
    "/refund/apply",
    response_model=BaseResponse[ClientRefundReversalReceiptView],
)
# Kept cohesive because FastAPI must expose the full authenticated command edge.
def apply_refund(
    body: ClientRefundApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    _refund_selection(case_no, body),
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "成功套用客戶退款",
        correlation,
    )


@router.post(
    "/refund-overage/preview",
    response_model=BaseResponse[ClientRefundReversalPreviewView],
)
def preview_refund_overage(
    body: ClientRefundPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-refund-overage-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_refund_overage_selection(case_no, body), correlation)
        ),
        "成功產生客戶退款超額追償預覽",
        correlation,
    )


@router.post(
    "/refund-overage/apply",
    response_model=BaseResponse[ClientRefundReversalReceiptView],
)
def apply_refund_overage(
    body: ClientRefundApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    _refund_overage_selection(case_no, body),
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "已建立客戶退款超額追償應收",
        correlation,
    )


@router.post(
    "/refund-overage-recovery/preview",
    response_model=BaseResponse[ClientOverRefundRecoveryPreviewView],
)
def preview_refund_overage_recovery(
):
    _raise_unmatched_recovery_retired()


@router.post(
    "/refund-overage-recovery/apply",
    response_model=BaseResponse[ClientOverRefundRecoveryReceiptView],
)
def apply_refund_overage_recovery(
):
    _raise_unmatched_recovery_retired()


@router.post(
    "/refund-overage-recovery/matched/preview",
    response_model=BaseResponse[ClientOverRefundRecoveryPreviewView],
)
def preview_matched_refund_overage_recovery(
    body: ClientOverRefundRecoveryMatchedPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-over-refund-recovery-matched-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientOverRefundRecoveryApplication = Depends(get_client_over_refund_recovery_application),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_recovery(
        lambda: _recovery_preview_payload(
            application.preview(_matched_recovery_selection(case_no, body), correlation)
        ),
        "成功產生已配對客戶追償收款預覽", correlation,
    )


@router.post(
    "/refund-overage-recovery/matched/apply",
    response_model=BaseResponse[ClientOverRefundRecoveryReceiptView],
)
def apply_matched_refund_overage_recovery(
    body: ClientOverRefundRecoveryMatchedApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientOverRefundRecoveryApplication = Depends(get_client_over_refund_recovery_application),
):
    correlation = CorrelationId(correlation_id)
    request = ClientOverRefundRecoveryApplyRequest(
        _matched_recovery_selection(case_no, body),
        ExpectedVersion(body.expected_recovery_version), ExpectedVersion(body.expected_account_version),
        PreviewFingerprint(body.preview_fingerprint), IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()), body.reason.strip(), correlation,
    )
    return _call_recovery(
        lambda: _materialize(application.apply(request)), "已核銷已配對客戶追償入款", correlation
    )


@router.post(
    "/refund-overage-recovery/adjustment/preview",
    response_model=BaseResponse[ClientOverRefundRecoveryAdjustmentPreviewView],
)
def preview_refund_overage_recovery_adjustment(
    body: ClientOverRefundRecoveryAdjustmentPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-over-refund-recovery-adjustment-preview",
    principal: AdminPrincipal = Depends(
        require_capability("client_finance.recovery.adjust")
    ),
    application: ClientOverRefundRecoveryApplication = Depends(
        get_client_over_refund_recovery_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_recovery(
        lambda: _recovery_adjustment_preview_payload(
            application.preview(_recovery_adjustment_selection(case_no, body), correlation)
        ),
        "成功產生客戶退款超額追償調整預覽",
        correlation,
    )


@router.post(
    "/refund-overage-recovery/adjustment/apply",
    response_model=BaseResponse[ClientOverRefundRecoveryReceiptView],
)
def apply_refund_overage_recovery_adjustment(
    body: ClientOverRefundRecoveryAdjustmentApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(
        require_capability("client_finance.recovery.adjust")
    ),
    application: ClientOverRefundRecoveryApplication = Depends(
        get_client_over_refund_recovery_application
    ),
):
    correlation = CorrelationId(correlation_id)
    request = ClientOverRefundRecoveryApplyRequest(
        _recovery_adjustment_selection(case_no, body),
        ExpectedVersion(body.expected_recovery_version),
        ExpectedVersion(body.expected_account_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        correlation,
    )
    return _call_recovery(
        lambda: _materialize(application.apply(request)),
        "已套用客戶退款超額追償調整",
        correlation,
    )


@router.post(
    "/refund-overage-recovery/matching/preview",
    response_model=BaseResponse[ClientOverRefundRecoveryMatchingPreviewView],
)
def preview_refund_overage_recovery_matching(
    body: ClientOverRefundRecoveryMatchingPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-over-refund-recovery-matching-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientOverRefundRecoveryApplication = Depends(get_client_over_refund_recovery_application),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_matching(
        lambda: _matching_preview_payload(
            application.preview_matching(_matching_selection(case_no, body), correlation)
        ),
        "成功產生客戶追償入款配對預覽",
        correlation,
    )


@router.post(
    "/refund-overage-recovery/matching/apply",
    response_model=BaseResponse[ClientOverRefundRecoveryMatchingReceiptView],
)
def apply_refund_overage_recovery_matching(
    body: ClientOverRefundRecoveryMatchingApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientOverRefundRecoveryApplication = Depends(get_client_over_refund_recovery_application),
):
    correlation = CorrelationId(correlation_id)
    request = ClientOverRefundRecoveryMatchingApplyRequest(
        _matching_selection(case_no, body),
        ExpectedVersion(body.expected_recovery_version),
        ExpectedVersion(body.expected_account_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        correlation,
    )
    return _call_matching(
        lambda: _materialize(application.apply_matching(request)),
        "已建立客戶追償入款配對",
        correlation,
    )


@router.post(
    "/subsidy-return/preview",
    response_model=BaseResponse[ClientRefundReversalPreviewView],
)
# Kept cohesive because FastAPI must expose the complete authenticated intent edge.
def preview_subsidy_return(
    body: ClientRefundPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-subsidy-return-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    selection = _refund_selection(
        case_no,
        body,
        ClientRefundPurpose.SUBSIDY_RETURN,
    )
    return _call(
        lambda: _preview_payload(application.preview(selection, correlation)),
        "成功產生客戶補助退還預覽",
        correlation,
    )


@router.post(
    "/subsidy-return/apply",
    response_model=BaseResponse[ClientRefundReversalReceiptView],
)
# Kept cohesive because FastAPI must expose the full authenticated command edge.
def apply_subsidy_return(
    body: ClientRefundApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    correlation = CorrelationId(correlation_id)
    selection = _refund_selection(
        case_no,
        body,
        ClientRefundPurpose.SUBSIDY_RETURN,
    )
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    selection,
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "成功套用客戶補助退還",
        correlation,
    )


@router.post(
    "/refund-return/preview",
    response_model=BaseResponse[ClientRefundReversalPreviewView],
)
def preview_refund_return(
    body: ClientRefundReturnPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-refund-return-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_refund_return_selection(case_no, body), correlation)
        ),
        "成功產生客戶退款退匯預覽",
        correlation,
    )


@router.post(
    "/refund-return/apply",
    response_model=BaseResponse[ClientRefundReversalReceiptView],
)
def apply_refund_return(
    body: ClientRefundReturnApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    _refund_return_selection(case_no, body),
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "成功套用客戶退款退匯",
        correlation,
    )


@router.post(
    "/reversal/preview",
    response_model=BaseResponse[ClientRefundReversalPreviewView],
)
def preview_reversal(
    body: ClientReversalPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    correlation_id: _CorrelationHeader = "client-reversal-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _preview_payload(
            application.preview(_reversal_selection(case_no, body), correlation)
        ),
        "成功產生客戶收款沖正預覽",
        correlation,
    )


@router.post(
    "/reversal/apply",
    response_model=BaseResponse[ClientRefundReversalReceiptView],
)
# Kept cohesive because FastAPI must expose the full authenticated command edge.
def apply_reversal(
    body: ClientReversalApplyBody,
    case_no: str = Path(..., min_length=1, max_length=191),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientRefundReversalApplication = Depends(
        get_client_refund_reversal_application
    ),
):
    correlation = CorrelationId(correlation_id)
    return _call(
        lambda: _materialize(
            application.apply(
                _apply_request(
                    _reversal_selection(case_no, body),
                    body,
                    idempotency_key,
                    correlation,
                    principal,
                )
            )
        ),
        "成功套用客戶收款沖正",
        correlation,
    )


def _refund_selection(
    case_no,
    body,
    refund_purpose=ClientRefundPurpose.CUSTOMER_REFUND,
):
    bank_ids = _canonical_integer_identities(body.finance_import_row_ids)
    obligation_ids = _canonical_text_identities(body.obligation_identities)
    return ClientRefundReversalSelection(
        case_no.strip(),
        ClientFinanceCorrectionType.REFUND,
        refund_purpose,
        bank_fact_identities=bank_ids,
        obligation_identities=obligation_ids,
        allow_partial_refund_recovery=body.allow_partial_refund_recovery,
    )


def _matched_recovery_selection(case_no, body):
    return ClientOverRefundRecoverySelection(
        case_no.strip(), body.recovery_identity.strip(), str(body.finance_import_row_id),
        matching_identity=body.matching_identity.strip(), matching_version=body.matching_version,
    )


def _raise_unmatched_recovery_retired() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "error": {
                "code": "client_over_refund_recovery_matching_required",
                "message": "追償收款必須先建立不可變入款配對。",
                "replacement": "/refund-overage-recovery/matching/preview",
            }
        },
    )


def _recovery_adjustment_selection(case_no, body):
    return ClientOverRefundRecoverySelection(
        case_no.strip(),
        body.recovery_identity.strip(),
        action=ClientOverRefundRecoveryAction.ADJUST,
        adjustment_amount=MoneyNTD(body.adjustment_amount_ntd),
    )


def _matching_selection(case_no, body):
    return ClientOverRefundRecoveryMatchingSelection(
        case_no.strip(), body.recovery_identity.strip(), str(body.finance_import_row_id)
    )


def _matching_preview_payload(preview):
    candidate = preview.candidate
    return {
        "recovery_identity": candidate.recovery_identity,
        "finance_import_row_identity": candidate.finance_import_row_identity,
        "recovery_version": candidate.recovery_version,
        "account_version": candidate.account_version,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _recovery_preview_payload(preview):
    candidate = preview.candidate
    return {
        "recovery_identity": candidate.recovery_identity,
        "account_version": preview.account_version,
        "recovery_version": preview.recovery_version,
        "amount_received_ntd": candidate.amount_received.amount,
        "remaining_before_ntd": candidate.remaining_before.amount,
        "remaining_after_ntd": candidate.remaining_after.amount,
        "resulting_status": candidate.resulting_status.value,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _recovery_adjustment_preview_payload(preview):
    candidate = preview.candidate
    return {
        "recovery_identity": candidate.recovery_identity,
        "account_version": preview.account_version,
        "recovery_version": preview.recovery_version,
        "adjustment_amount_ntd": candidate.adjustment_amount.amount,
        "remaining_before_ntd": candidate.remaining_before.amount,
        "remaining_after_ntd": candidate.remaining_after.amount,
        "resulting_status": candidate.resulting_status.value,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _refund_overage_selection(case_no, body):
    return ClientRefundReversalSelection(
        case_no.strip(),
        ClientFinanceCorrectionType.REFUND_OVERAGE,
        ClientRefundPurpose.CUSTOMER_REFUND,
        bank_fact_identities=_canonical_integer_identities(body.finance_import_row_ids),
        obligation_identities=_canonical_text_identities(body.obligation_identities),
    )


def _reversal_selection(case_no, body):
    return ClientRefundReversalSelection(
        case_no.strip(),
        ClientFinanceCorrectionType.REVERSAL,
        reversal_target_identities=_canonical_integer_identities(
            body.ledger_entry_ids
        ),
        reversal_occurred_on=body.occurred_on.isoformat(),
    )


def _refund_return_selection(case_no, body):
    return ClientRefundReversalSelection(
        case_no.strip(),
        ClientFinanceCorrectionType.REFUND_RETURN,
        bank_fact_identities=(str(body.finance_import_row_id),),
        reversal_target_identities=(str(body.refund_ledger_entry_id),),
    )


def _apply_request(selection, body, key, correlation, principal):
    return ClientRefundReversalApplyRequest(
        selection,
        ExpectedVersion(body.expected_account_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        correlation,
    )


def _preview_payload(preview):
    return {
        "account_version": preview.account_version,
        "candidate": _materialize(preview.candidate),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _canonical_integer_identities(values):
    identities = tuple(str(value) for value in values)
    _require_unique(identities)
    return tuple(sorted(identities, key=int))


def _canonical_text_identities(values):
    identities = tuple(value.strip() for value in values)
    if any(not value for value in identities):
        raise ValueError("invalid_client_finance_intent")
    _require_unique(identities)
    return tuple(sorted(identities))


def _require_unique(values) -> None:
    if len(values) != len(set(values)):
        raise ValueError("invalid_client_finance_intent")


# Kept cohesive so every endpoint returns the same typed error envelope.
def _call(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except ClientRefundReversalError as error:
        _raise_typed(error.error)
    except ValueError as error:
        _raise_value_error(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        typed = TypedError(
            ErrorCategory.INTERNAL,
            "transaction_failed",
            "客戶退款或沖正交易失敗。",
            correlation,
        )
        raise _http_error(500, typed) from error


def _call_recovery(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except ClientOverRefundRecoveryError as error:
        _raise_typed(error.error)
    except ValueError as error:
        _raise_value_error(error, correlation)


def _call_matching(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except ClientOverRefundRecoveryMatchingError as error:
        _raise_typed(error.error)
    except ValueError as error:
        _raise_value_error(error, correlation)


def _raise_typed(error):
    error = canonicalize_client_finance_error(error)
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
    raise _http_error(status, error, headers)


def _raise_value_error(error, correlation):
    code = str(error) or "invalid_client_finance_intent"
    if code in {"client_finance_case_not_found", "client_obligation_not_found"}:
        category, status = ErrorCategory.NOT_FOUND, 404
    elif code == "invalid_client_finance_intent":
        category, status = ErrorCategory.VALIDATION, 422
    else:
        category, status = ErrorCategory.DOMAIN_BLOCKED, 409
    typed = TypedError(
        category,
        code,
        "客戶退款或沖正請求未通過驗證。",
        correlation,
        domain_blockers=(code,) if status == 409 else (),
    )
    raise _http_error(status, typed) from error


def _http_error(status, error, headers=None):
    return HTTPException(
        status_code=status,
        detail={"error": _materialize(error)},
        headers=headers,
    )


# Kept recursive so every typed HTTP payload uses one serialization rule.
def _materialize(value):
    if hasattr(value, "value") and value.__class__.__module__.startswith(
        ("shared_kernel.",)
    ):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _materialize(getattr(value, item.name))
            for item in fields(value)
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


__all__ = ["router"]

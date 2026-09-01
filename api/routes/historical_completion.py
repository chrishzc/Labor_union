"""
File: historical_completion.py
Description: 提供 authenticated HOB-E owner-terminal completion fresh Query API。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import (
    require_historical_order_review_remediator,
    require_system_admin,
)
from api.dependencies.historical_completion import (
    HistoricalCompletionApplication,
    get_historical_completion_application,
)
from api.schemas.base import BaseResponse
from api.schemas.historical_completion import (
    HistoricalCompletionApplyBody,
    HistoricalCompletionPreviewView,
    HistoricalCompletionReceiptView,
    HistoricalCompletionView,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_completion_projector import (
    HistoricalCompletionTerminalProjection,
)
from subsystems.orders.historical_completion_query import HistoricalCompletionQueryError
from subsystems.orders.historical_completion_apply import (
    ApplyHistoricalCompletion,
    HistoricalCompletionApplyError,
)
from subsystems.orders.historical_completion_oracle import (
    HistoricalSettlementSourceVersion,
    SettlementSourceKind,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])
_CorrelationHeader = Annotated[
    str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
]
_IdempotencyHeader = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=191)
]


@router.get(
    "/{case_no}/historical-completion",
    response_model=BaseResponse[HistoricalCompletionView],
)
def query_historical_completion(
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: _CorrelationHeader = "historical-completion-query",
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalCompletionApplication = Depends(
        get_historical_completion_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    try:
        projection = application.query(case_no.strip(), correlation)
    except HistoricalCompletionQueryError as error:
        status = 409 if error.error.category.value == "conflict" else 422
        raise HTTPException(
            status_code=status,
            detail={
                "code": error.error.code,
                "message": error.error.message,
                "domain_blockers": list(error.error.domain_blockers),
                "correlation_id": error.error.correlation_id.value,
            },
        ) from error
    return BaseResponse(
        data=_projection_payload(projection),
        message="成功載入歷史案件 owner-terminal completion",
    )


@router.post(
    "/{case_no}/historical-completion/preview",
    response_model=BaseResponse[HistoricalCompletionPreviewView],
)
def preview_historical_completion(
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: _CorrelationHeader = "historical-completion-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: HistoricalCompletionApplication = Depends(
        get_historical_completion_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _mutating_call(
        lambda: BaseResponse(
            data=_preview_payload(application.preview(case_no.strip())),
            message="歷史訂單帳務完成 Preview 已完成",
        ),
        correlation,
    )


@router.post(
    "/{case_no}/historical-completion/apply",
    response_model=BaseResponse[HistoricalCompletionReceiptView],
)
def apply_historical_completion(
    body: HistoricalCompletionApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: HistoricalCompletionApplication = Depends(
        get_historical_completion_application
    ),
):
    correlation = CorrelationId(correlation_id)
    request = ApplyHistoricalCompletion(
        case_no.strip(),
        int(body.expected_order_version),
        int(body.expected_client_finance_version),
        tuple(
            sorted(
                HistoricalSettlementSourceVersion(
                    SettlementSourceKind(item.kind), item.identity.strip(), int(item.version)
                )
                for item in body.expected_source_versions
            )
        ),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        correlation,
    )
    return _mutating_call(
        lambda: BaseResponse(
            data=_receipt_payload(application.apply(request)),
            message="歷史訂單已推進至帳務完成",
        ),
        correlation,
    )


def _projection_payload(
    projection: HistoricalCompletionTerminalProjection,
) -> dict[str, object]:
    return {
        "case_no": projection.case_no,
        "state": projection.state.value,
        "step_11_status": projection.step_11_status,
        "step_11_completed": projection.step_11_completed,
        "historical_alerts_completed": projection.historical_alerts_completed,
        "active_alerts": [
            {
                "code": alert.code,
                "owner": alert.owner.value,
                "field_path": alert.field_path,
                "referral": alert.referral.value,
                "message": alert.message,
            }
            for alert in projection.active_alerts
        ],
        "owner_versions": [
            {"owner": owner, "version": str(version)}
            for owner, version in projection.owner_versions
        ],
        "owner_source_versions": [
            {
                "kind": source.kind.value,
                "identity": source.identity,
                "version": str(source.version),
            }
            for source in projection.owner_source_versions
        ],
        "source_fingerprint": projection.source_fingerprint.value,
        "projection_fingerprint": projection.projection_fingerprint.value,
    }


def _preview_payload(candidate) -> dict[str, object]:
    return {
        "case_no": candidate.case_no,
        "before_status": candidate.before_status.value,
        "after_status": candidate.after_status.value,
        "expected_order_version": str(candidate.expected_order_version),
        "resulting_order_version": str(candidate.resulting_order_version),
        "expected_client_finance_version": str(candidate.expected_client_finance_version),
        "expected_source_versions": [
            {
                "kind": item.kind.value,
                "identity": item.identity,
                "version": str(item.version),
            }
            for item in candidate.expected_source_versions
        ],
        "business_date": candidate.business_date.isoformat(),
        "preview_fingerprint": candidate.fingerprint.value,
    }


def _receipt_payload(receipt) -> dict[str, object]:
    return {
        "case_no": receipt.case_no,
        "lifecycle_event_id": receipt.lifecycle_event_id,
        "resulting_order_version": str(receipt.resulting_order_version),
        "after_status": receipt.after_status.value,
        "replayed": receipt.replayed,
    }


def _mutating_call(command, correlation: CorrelationId):
    try:
        return command()
    except HistoricalCompletionApplyError as error:
        _raise_typed(error.error)
    except ValueError as error:
        code = str(error) or "historical_accounting_completion_blocked"
        category = (
            ErrorCategory.NOT_FOUND
            if code == "historical_order_not_found"
            else ErrorCategory.DOMAIN_BLOCKED
        )
        _raise_typed(
            TypedError(
                category,
                code,
                "歷史訂單帳務完成狀態未通過驗證。",
                correlation,
                domain_blockers=(code,),
            )
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "category": "internal",
                    "code": "transaction_failed",
                    "message": "歷史訂單帳務完成交易失敗。",
                    "correlation_id": correlation.value,
                }
            },
        ) from error


def _raise_typed(error: TypedError) -> None:
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
    raise HTTPException(
        status_code=status,
        detail={
            "error": {
                "category": error.category.value,
                "code": error.code,
                "message": error.message,
                "field_errors": [],
                "domain_blockers": list(error.domain_blockers),
                "retryable": error.retryable,
                "correlation_id": error.correlation_id.value,
                "current_version": (
                    None if error.current_version is None else error.current_version.value
                ),
            }
        },
    )


__all__ = ["router"]

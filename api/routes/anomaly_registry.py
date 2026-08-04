"""Authenticated query and workflow endpoints for Anomalies."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.anomaly_registry import get_anomaly_application
from api.schemas.anomaly_registry import (
    AnomalyDetailView,
    AnomalySummaryView,
    AnomalyWorkflowReceiptView,
    ClaimAnomalyBody,
    ResolveAnomalyBody,
)
from api.schemas.base import BaseResponse
from infrastructure.mysql.anomaly_registry_repository import (
    AnomalyRepositoryUnavailable,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    IdempotencyKey,
)
from subsystems.anomalies.alert_workflow import (
    AnomalyApplication,
    AnomalyWorkflowError,
    AnomalyWorkflowRequest,
)

router = APIRouter(prefix="/api/v1/anomalies", tags=["Anomalies"])
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


@router.get("", response_model=BaseResponse[list[AnomalySummaryView]])
def query_anomalies(
    active_only: bool = Query(True),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_snapshot: bool = Query(False),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AnomalyApplication = Depends(get_anomaly_application),
):
    del principal
    correlation = CorrelationId("anomaly-query")
    return _call(
        lambda: [
            _summary_payload(item, include_snapshot=include_snapshot)
            for item in application.query_summaries(
                active_only=active_only,
                limit=limit,
                offset=offset,
            )
        ],
        "成功取得異常摘要",
        correlation,
    )


@router.get(
    "/{fingerprint}",
    response_model=BaseResponse[AnomalyDetailView],
)
def query_anomaly_detail(
    fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AnomalyApplication = Depends(get_anomaly_application),
):
    del principal
    correlation = CorrelationId(f"anomaly-detail:{fingerprint}")
    return _call(
        lambda: _detail_payload(
            application.query_detail(PreviewFingerprint(fingerprint))
        ),
        "成功取得異常詳情",
        correlation,
    )


@router.post(
    "/{fingerprint}/claim",
    response_model=BaseResponse[AnomalyWorkflowReceiptView],
)
# Kept explicit so authenticated actor and command identity stay server-owned.
def claim_anomaly(
    body: ClaimAnomalyBody,
    fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AnomalyApplication = Depends(get_anomaly_application),
):
    request = _workflow_request(
        fingerprint,
        body.expected_workflow_version,
        idempotency_key,
        correlation_id,
        principal,
        "Claimed for human review.",
    )
    return _call(
        lambda: _materialize(application.claim(request)),
        "成功認領異常",
        request.correlation_id,
    )


@router.post(
    "/{fingerprint}/resolve",
    response_model=BaseResponse[AnomalyWorkflowReceiptView],
)
# Kept explicit so resolution reason and version cross one typed boundary.
def resolve_anomaly(
    body: ResolveAnomalyBody,
    fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AnomalyApplication = Depends(get_anomaly_application),
):
    request = _workflow_request(
        fingerprint,
        body.expected_workflow_version,
        idempotency_key,
        correlation_id,
        principal,
        body.reason.strip(),
    )
    return _call(
        lambda: _materialize(application.resolve(request)),
        "成功更新異常處理進度",
        request.correlation_id,
    )


def _workflow_request(
    fingerprint,
    expected_version,
    key,
    correlation,
    principal,
    reason,
):
    return AnomalyWorkflowRequest(
        PreviewFingerprint(fingerprint),
        expected_version,
        IdempotencyKey(key),
        ActorContext(str(principal.username or "").strip()),
        reason,
        CorrelationId(correlation),
    )


def _summary_payload(summary, *, include_snapshot=True):
    projection = summary.projection
    return {
        "fingerprint": projection.fingerprint.value,
        "definition_code": projection.definition_code,
        "source_domain": summary.source_domain,
        "source_identity": projection.source_identity,
        "source_version": projection.source_version,
        "severity": summary.severity,
        "predicate_active": projection.predicate_active,
        "workflow_status": projection.workflow_status.value,
        "workflow_version": projection.workflow_version,
        **(
            {"display_snapshot": dict(summary.display_snapshot)}
            if include_snapshot
            else {}
        ),
    }


def _detail_payload(detail):
    return {
        "summary": _summary_payload(detail.summary),
        "timeline": _materialize(detail.timeline),
        "available_actions": _materialize(detail.available_actions),
    }


def _call(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except AnomalyWorkflowError as error:
        _raise_typed(error.error)
    except AnomalyRepositoryUnavailable as error:
        _raise_unavailable(error, correlation)
    except OperationalError as error:
        _raise_mysql(error, correlation)
    except ValueError as error:
        _raise_value_error(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation) from error


def _raise_typed(error: TypedError):
    status = {
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.FORBIDDEN: 403,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.UNAVAILABLE: 503,
        ErrorCategory.INTERNAL: 500,
    }[error.category]
    raise _http_error(status, error)


def _raise_unavailable(error, correlation):
    typed = TypedError(
        ErrorCategory.UNAVAILABLE,
        "projector_unavailable",
        "異常投影暫時無法完成，請沿用相同冪等鍵重試。",
        correlation,
        retryable=True,
    )
    raise _http_error(503, typed, {"Retry-After": "1"}) from error


def _raise_mysql(error, correlation):
    retryable = bool(error.args and int(error.args[0]) in {1205, 1213})
    typed = TypedError(
        ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
        "transaction_failed",
        "異常工作流資料庫交易失敗。",
        correlation,
        retryable=retryable,
    )
    headers = {"Retry-After": "1"} if retryable else None
    raise _http_error(503 if retryable else 500, typed, headers) from error


def _raise_value_error(error, correlation):
    code = str(error) or "anomaly_projection_data_integrity_violation"
    status = 404 if code == "anomaly_not_found" else 422
    category = ErrorCategory.NOT_FOUND if status == 404 else ErrorCategory.VALIDATION
    typed = TypedError(category, code, "異常資料未通過驗證。", correlation)
    raise _http_error(status, typed) from error


def _internal_error(correlation):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "transaction_failed",
            "異常工作流交易失敗。",
            correlation,
        ),
    )


def _http_error(status, error, headers=None):
    return HTTPException(
        status_code=status,
        detail={"error": _materialize(error)},
        headers=headers,
    )


# Kept recursive so typed query and workflow payloads share one rule.
def _materialize(value):
    if isinstance(
        value,
        (CorrelationId, IdempotencyKey, PreviewFingerprint),
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
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value


__all__ = ["router"]

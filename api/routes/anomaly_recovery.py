"""Read-only typed recovery routes for root-fact anomalies."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.anomaly_recovery import (
    get_anomaly_maintenance_application,
    get_anomaly_recovery_application,
)
from api.schemas.anomaly_recovery import (
    AnomalyRecoveryContextView,
    RecoveryActionView,
    RetryAnomalyProjectorBody,
    RetryAnomalyProjectorResultView,
    ScanAnomalyDefinitionBody,
    ScanAnomalyDefinitionResultView,
)
from api.schemas.base import BaseResponse
from domains.anomalies.maintenance import (
    RetryAnomalyProjectorRequest,
    ScanAnomalyDefinitionRequest,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.anomalies.maintenance_workflow import (
    AnomalyMaintenanceApplication,
    AnomalyMaintenanceError,
)
from subsystems.anomalies.root_fact_projection_workflow import (
    RootFactProjectionApplication,
    RootFactProjectionError,
)

router = APIRouter(prefix="/api/v1/anomaly-recovery", tags=["Anomalies"])


# The typed HTTP signature remains explicit so FastAPI documents every boundary.
@router.post(
    "/definitions/{definition_code}/scan",
    response_model=BaseResponse[ScanAnomalyDefinitionResultView],
)
def scan_anomaly_definition(
    body: ScanAnomalyDefinitionBody,
    definition_code: str = Path(..., min_length=1, max_length=191),
    correlation_header: str | None = Header(
        default=None,
        alias="X-Correlation-ID",
    ),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AnomalyMaintenanceApplication = Depends(
        get_anomaly_maintenance_application
    ),
):
    del principal
    correlation_id = _correlation_id(
        correlation_header,
        f"anomaly-scan:{definition_code}",
    )
    request = ScanAnomalyDefinitionRequest(
        definition_code,
        body.maximum_items,
        body.after_source_id,
    )
    return _call_maintenance(
        lambda: _scan_result_payload(
            application.scan_definition(request, correlation_id)
        ),
        "完成異常根事實分頁重掃描",
    )


# The typed HTTP signature remains explicit so FastAPI documents every boundary.
@router.post(
    "/projector/retry",
    response_model=BaseResponse[RetryAnomalyProjectorResultView],
)
def retry_anomaly_projector(
    body: RetryAnomalyProjectorBody,
    correlation_header: str | None = Header(
        default=None,
        alias="X-Correlation-ID",
    ),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AnomalyMaintenanceApplication = Depends(
        get_anomaly_maintenance_application
    ),
):
    del principal
    correlation_id = _correlation_id(
        correlation_header,
        "anomaly-projector-retry",
    )
    request = RetryAnomalyProjectorRequest(body.maximum_events)
    return _call_maintenance(
        lambda: _retry_result_payload(
            application.retry_projector(request, correlation_id)
        ),
        "已重新排入失敗的異常 projector 事件",
    )


@router.get(
    "/{fingerprint}",
    response_model=BaseResponse[AnomalyRecoveryContextView],
)
def query_recovery_context(
    fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: RootFactProjectionApplication = Depends(
        get_anomaly_recovery_application
    ),
):
    del principal
    correlation_id = CorrelationId(f"anomaly-recovery:{fingerprint}")
    return _call(
        lambda: _context_payload(
            application.query_recovery(
                PreviewFingerprint(fingerprint),
                correlation_id,
            )
        ),
        "成功取得異常修復資訊",
    )


@router.get(
    "/{fingerprint}/actions/{action_code}",
    response_model=BaseResponse[RecoveryActionView],
)
def query_recovery_preview_link(
    fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    action_code: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: RootFactProjectionApplication = Depends(
        get_anomaly_recovery_application
    ),
):
    del principal
    correlation_id = CorrelationId(f"recovery-action:{fingerprint}")
    return _call(
        lambda: _materialize(
            application.query_recovery_preview_link(
                PreviewFingerprint(fingerprint),
                action_code,
                correlation_id,
            )
        ),
        "成功取得 owning Domain Preview 入口",
    )


def _context_payload(context):
    projection = context.projection
    return {
        "fingerprint": projection.fingerprint.value,
        "definition_code": projection.definition_code,
        "source_domain": context.source_domain,
        "source_identity": projection.source_identity,
        "source_version": projection.source_version,
        "severity": context.severity,
        "predicate_active": projection.predicate_active,
        "workflow_status": projection.workflow_status.value,
        "workflow_version": projection.workflow_version,
        "domain_blocker_active": context.domain_blocker_active,
        "projection_freshness": context.projection_freshness,
        "root_fact_snapshot": context.root_fact_snapshot,
        "occurrence_timeline": _materialize(context.occurrence_timeline),
        "workflow_timeline": _materialize(context.workflow_timeline),
        "available_actions": _materialize(context.available_actions),
    }


def _call(query, message):
    try:
        return BaseResponse(data=query(), message=message)
    except RootFactProjectionError as error:
        raise _http_error(error) from error


def _call_maintenance(command, message):
    try:
        return BaseResponse(data=command(), message=message)
    except (AnomalyMaintenanceError, RootFactProjectionError) as error:
        raise _http_error(error) from error


def _scan_result_payload(result):
    return {
        "definition_code": result.definition_code,
        "scanned_count": result.scanned_count,
        "active_count": result.active_count,
        "inactive_count": result.inactive_count,
        "next_after_source_id": result.next_after_source_id,
        "completed": result.completed,
    }


def _retry_result_payload(result):
    return {
        "projector_identity": result.projector_identity,
        "requeued_event_ids": list(result.requeued_event_ids),
        "requeued_count": result.requeued_count,
    }


def _correlation_id(value, fallback):
    return CorrelationId(value.strip() if value and value.strip() else fallback)


def _http_error(error):
    status = {
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.UNAVAILABLE: 503,
    }.get(error.error.category, 500)
    headers = {"Retry-After": "1"} if error.error.retryable else None
    return HTTPException(
        status_code=status,
        detail={"error": _materialize(error.error)},
        headers=headers,
    )


def _materialize(value):
    if isinstance(value, (PreviewFingerprint, CorrelationId)):
        return value.value
    if isinstance(value, ExpectedVersion):
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

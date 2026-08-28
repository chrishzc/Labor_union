"""
File: anomaly_necessity_migration.py
Description: 提供 server-owned policy 的異常必要性移轉維運 Query／Preview／Apply API。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_anomaly_necessity_migration_operator,
)
from api.dependencies.anomaly_necessity_migration import (
    AnomalyNecessityMigrationApplication,
    get_anomaly_necessity_migration_application,
)
from api.schemas.anomaly_necessity_migration import (
    AnomalyNecessityMigrationApplyBody,
    AnomalyNecessityMigrationErrorEnvelopeView,
    AnomalyNecessityMigrationIntentBody,
    AnomalyNecessityMigrationPageView,
    AnomalyNecessityMigrationPreviewView,
    AnomalyNecessityMigrationReceiptView,
)
from api.schemas.base import BaseResponse
from domains.anomalies.maintenance import (
    AnomalyReclassificationAlertIdentity,
    AnomalyReclassificationApplyRequest,
    AnomalyReclassificationCursor,
    AnomalyReclassificationCursorPageRequest,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.anomalies.maintenance_workflow import AnomalyMaintenanceError


router = APIRouter(
    prefix="/api/v1/admin/anomaly-necessity-migration",
    tags=["Anomalies Maintenance"],
)
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_ERROR_RESPONSES = {
    status: {"model": AnomalyNecessityMigrationErrorEnvelopeView}
    for status in (403, 404, 409, 422, 500, 503)
}


@router.get(
    "/alerts",
    response_model=BaseResponse[AnomalyNecessityMigrationPageView],
    responses=_ERROR_RESPONSES,
)
def query_anomaly_necessity_migration_alerts(
    maximum_items: int = Query(default=100, ge=1, le=100),
    after_definition_code: str | None = Query(
        default=None,
        min_length=1,
        max_length=191,
    ),
    after_source_identity: str | None = Query(
        default=None,
        min_length=1,
        max_length=191,
    ),
    principal: AdminPrincipal = Depends(
        require_anomaly_necessity_migration_operator
    ),
    application: AnomalyNecessityMigrationApplication = Depends(
        get_anomaly_necessity_migration_application
    ),
):
    del principal
    correlation = CorrelationId("anomaly-necessity-migration-query")
    return _call(
        lambda: _page_payload(
            application,
            maximum_items,
            after_definition_code,
            after_source_identity,
        ),
        "成功取得核准異常必要性移轉清單",
        correlation,
    )


@router.post(
    "/alerts/{alert_fingerprint}/preview",
    response_model=BaseResponse[AnomalyNecessityMigrationPreviewView],
    responses=_ERROR_RESPONSES,
)
def preview_anomaly_necessity_migration(
    body: AnomalyNecessityMigrationIntentBody,
    alert_fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    correlation_header: str | None = Header(
        default=None,
        alias="X-Correlation-ID",
        min_length=1,
        max_length=191,
    ),
    principal: AdminPrincipal = Depends(
        require_anomaly_necessity_migration_operator
    ),
    application: AnomalyNecessityMigrationApplication = Depends(
        get_anomaly_necessity_migration_application
    ),
):
    correlation = CorrelationId(
        correlation_header
        or f"anomaly-necessity-migration-preview:{alert_fingerprint}"
    )
    alert = _alert_from_body(alert_fingerprint, body)
    return _call(
        lambda: _preview_payload(
            application,
            alert,
            admin_actor_context(principal),
            body.reason,
            body.evidence_reference,
        ),
        "成功預覽核准異常必要性移轉",
        correlation,
    )


@router.post(
    "/alerts/{alert_fingerprint}/apply",
    response_model=BaseResponse[AnomalyNecessityMigrationReceiptView],
    responses=_ERROR_RESPONSES,
)
def apply_anomaly_necessity_migration(
    body: AnomalyNecessityMigrationApplyBody,
    alert_fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_header: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(
        require_anomaly_necessity_migration_operator
    ),
    application: AnomalyNecessityMigrationApplication = Depends(
        get_anomaly_necessity_migration_application
    ),
):
    correlation = CorrelationId(correlation_header)
    alert = _alert_from_body(alert_fingerprint, body)
    return _call(
        lambda: _apply_payload(
            application,
            alert,
            admin_actor_context(principal),
            body,
            IdempotencyKey(idempotency_key),
            correlation,
        ),
        "已套用核准異常必要性移轉",
        correlation,
    )


def _page_payload(
    application: AnomalyNecessityMigrationApplication,
    maximum_items: int,
    after_definition_code: str | None,
    after_source_identity: str | None,
):
    if (after_definition_code is None) != (after_source_identity is None):
        raise ValueError("anomaly_necessity_migration_cursor_incomplete")
    cursor = (
        None
        if after_definition_code is None
        else AnomalyReclassificationCursor(
            after_definition_code,
            after_source_identity,
        )
    )
    page = application.workflow.query_reclassification(
        AnomalyReclassificationCursorPageRequest(maximum_items, cursor),
        eligible_codes=application.policy.eligible_codes,
    )
    return {
        "items": [_alert_payload(item) for item in page.items],
        "next_cursor": (
            None
            if page.next_cursor is None
            else {
                "definition_code": page.next_cursor.definition_code,
                "source_identity": page.next_cursor.source_identity,
            }
        ),
        "policy_identity": application.policy.identity,
        "policy_fingerprint": application.policy.fingerprint.value,
    }


def _preview_payload(application, alert, actor, reason, evidence_reference):
    candidate = _server_preview(
        application,
        alert,
        actor,
        reason,
        evidence_reference,
    )
    return _candidate_payload(application, candidate)


def _apply_payload(
    application,
    alert,
    actor,
    body,
    idempotency_key,
    correlation,
):
    candidate = application.policy.build_candidate(
        alert,
        actor=actor,
        reason=body.reason,
        evidence_reference=body.evidence_reference,
    )
    if candidate.fingerprint != PreviewFingerprint(body.preview_fingerprint):
        raise ValueError("anomaly_reclassification_preview_stale")
    request = AnomalyReclassificationApplyRequest.from_preview(
        candidate,
        idempotency_key=idempotency_key,
        correlation_id=correlation,
    )
    receipt = application.workflow.apply_reclassification(request)
    return {
        "disposition_identity": receipt.disposition_identity,
        "receipt_identity": receipt.receipt_identity,
        "disposition": receipt.disposition,
        "alert": _alert_payload(receipt.alert),
        "policy_identity": application.policy.identity,
        "policy_fingerprint": application.policy.fingerprint.value,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "idempotency_key": receipt.idempotency_key.value,
        "correlation_id": receipt.correlation_id.value,
        "created_at": receipt.created_at,
        "workflow_event_id": receipt.workflow_event_id,
        "resulting_workflow_version": receipt.resulting_workflow_version,
        "before_state_fingerprint": receipt.before_state_fingerprint.value,
        "after_state_fingerprint": receipt.after_state_fingerprint.value,
        "resulting_predicate_active": receipt.resulting_predicate_active,
        "replayed": receipt.replayed,
    }


def _server_preview(application, alert, actor, reason, evidence_reference):
    policy_candidate = application.policy.build_candidate(
        alert,
        actor=actor,
        reason=reason,
        evidence_reference=evidence_reference,
    )
    return application.workflow.preview_reclassification(
        alert,
        policy_candidate.disposition,
        policy_candidate.target,
        actor,
        reason,
        evidence_reference,
        policy_candidate.rulebook_reference,
        policy_candidate.release_evidence_reference,
    )


def _candidate_payload(application, candidate):
    target = candidate.target
    return {
        "disposition_identity": candidate.disposition_identity,
        "disposition": candidate.disposition,
        "alert": _alert_payload(candidate.alert),
        "target": (
            None
            if target is None
            else {
                "target_domain": target.target_domain,
                "target_reference": target.target_reference,
                "target_version": target.target_version,
            }
        ),
        "rulebook_reference": candidate.rulebook_reference,
        "release_evidence_reference": candidate.release_evidence_reference,
        "policy_identity": application.policy.identity,
        "policy_fingerprint": application.policy.fingerprint.value,
        "preview_fingerprint": candidate.fingerprint.value,
    }


def _alert_from_body(alert_fingerprint, body):
    return AnomalyReclassificationAlertIdentity(
        PreviewFingerprint(alert_fingerprint),
        body.expected_definition_code,
        body.expected_source_identity,
        body.expected_source_version,
        body.expected_workflow_version,
    )


def _alert_payload(alert):
    return {
        "alert_fingerprint": alert.alert_fingerprint.value,
        "definition_code": alert.definition_code,
        "source_identity": alert.source_identity,
        "source_version": alert.source_version,
        "workflow_version": alert.workflow_version,
    }


def _call(operation, message, correlation):
    try:
        return BaseResponse(data=operation(), message=message)
    except AnomalyMaintenanceError as error:
        raise _typed_http_error(
            503,
            ErrorCategory.UNAVAILABLE,
            "anomaly_necessity_migration_unavailable",
            "異常必要性移轉暫時無法完成。",
            correlation,
            retryable=True,
        ) from error
    except (TypeError, ValueError) as error:
        raise _contract_http_error(str(error), correlation) from error


def _contract_http_error(code, correlation):
    status, category, message = {
        "anomaly_reclassification_alert_not_found": (
            404,
            ErrorCategory.NOT_FOUND,
            "找不到待移轉的異常。",
        ),
        "anomaly_necessity_migration_definition_not_admitted": (
            409,
            ErrorCategory.DOMAIN_BLOCKED,
            "此異常尚未納入核准的移轉 policy。",
        ),
        "anomaly_reclassification_target_not_found": (
            409,
            ErrorCategory.DOMAIN_BLOCKED,
            "找不到可操作的 owner target。",
        ),
        "anomaly_reclassification_stale_target": (
            409,
            ErrorCategory.CONFLICT,
            "Owner target 已變更，請重新查詢與預覽。",
        ),
        "anomaly_reclassification_stale_alert": (
            409,
            ErrorCategory.CONFLICT,
            "異常版本已變更，請重新查詢與預覽。",
        ),
        "anomaly_reclassification_alert_stale": (
            409,
            ErrorCategory.CONFLICT,
            "異常版本已變更，請重新查詢與預覽。",
        ),
        "anomaly_reclassification_preview_stale": (
            409,
            ErrorCategory.CONFLICT,
            "移轉預覽已過期，請重新預覽。",
        ),
        "anomaly_reclassification_idempotency_conflict": (
            409,
            ErrorCategory.IDEMPOTENCY_MISMATCH,
            "此 Idempotency-Key 已用於不同的移轉內容。",
        ),
    }.get(
        code,
        (
            422,
            ErrorCategory.VALIDATION,
            "異常必要性移轉資料未通過驗證。",
        ),
    )
    return _typed_http_error(status, category, code or "invalid_request", message, correlation)


def _typed_http_error(
    status,
    category,
    code,
    message,
    correlation,
    *,
    retryable=False,
):
    return HTTPException(
        status_code=status,
        detail={
            "error": {
                "category": category.value,
                "code": code,
                "message": message,
                "field_errors": [],
                "domain_blockers": [],
                "retryable": retryable,
                "correlation_id": correlation.value,
                "current_version": None,
            }
        },
    )


__all__ = ["router"]

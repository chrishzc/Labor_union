"""Authenticated storage-retention Query, zero-write Preview and Apply API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies.admin_auth import admin_actor_context, require_root
from api.dependencies.operational_retention import operational_retention_application
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.operational_retention import (
    RetentionApplyRequest,
    RetentionDashboardView,
    RetentionPreviewRequest,
    RetentionPreviewView,
    RetentionReceiptView,
    RetentionSourceView,
)
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.runtime_governance.operational_retention import (
    OperationalRetentionApplication,
    POLICY_REVISION,
    RETENTION_DAYS,
    RetentionError,
)


router = APIRouter(prefix="/api/v1/system/storage-retention", tags=["Operational Retention"])


@router.get("", response_model=BaseResponse[RetentionDashboardView])
def retention_dashboard(
    _=Depends(require_root),
    application: OperationalRetentionApplication = Depends(operational_retention_application),
) -> BaseResponse[RetentionDashboardView]:
    try:
        sources = application.dashboard()
    except Exception as error:
        raise _unavailable("retention_dashboard_unavailable") from error
    return BaseResponse(
        data=RetentionDashboardView(
            policy_revision=POLICY_REVISION,
            retention_days=RETENTION_DAYS,
            sources=tuple(
                RetentionSourceView.model_validate(source, from_attributes=True)
                for source in sources
            ),
        )
    )


@router.post("/preview", response_model=BaseResponse[RetentionPreviewView])
def preview_retention(
    payload: RetentionPreviewRequest,
    _=Depends(require_root),
    application: OperationalRetentionApplication = Depends(operational_retention_application),
) -> BaseResponse[RetentionPreviewView]:
    try:
        preview = application.preview(
            source_id=payload.source_id,
            mode=payload.mode,
            reason=payload.reason,
            batch_size=payload.batch_size,
        )
    except RetentionError as error:
        raise _retention_error(error, "retention-preview") from error
    except Exception as error:
        raise _unavailable("retention_preview_unavailable") from error
    return BaseResponse(
        data=RetentionPreviewView(
            policy_revision=preview.policy_revision,
            source_id=preview.source_id,
            mode=preview.mode,
            reason=preview.reason,
            previewed_at_utc=preview.previewed_at_utc,
            cutoff_at_utc=preview.cutoff_at_utc,
            batch_size=preview.batch_size,
            candidate_count=preview.candidate_count,
            estimated_reclaimable_bytes=preview.estimated_reclaimable_bytes,
            current_logical_bytes=preview.current_logical_bytes,
            target_low_water_bytes=preview.target_low_water_bytes,
            preview_fingerprint=preview.preview_fingerprint.value,
        ),
        message="清理預覽已建立；尚未刪除任何資料。",
    )


@router.post("/apply", response_model=BaseResponse[RetentionReceiptView])
def apply_retention(
    payload: RetentionApplyRequest,
    request: Request,
    principal=Depends(require_root),
    application: OperationalRetentionApplication = Depends(operational_retention_application),
) -> BaseResponse[RetentionReceiptView]:
    actor = admin_actor_context(principal)
    try:
        receipt = application.apply(
            source_id=payload.source_id,
            mode=payload.mode,
            reason=payload.reason,
            batch_size=payload.batch_size,
            previewed_at_utc=payload.previewed_at_utc,
            preview_fingerprint=PreviewFingerprint(payload.preview_fingerprint),
            idempotency_key=payload.idempotency_key,
            correlation_id=payload.correlation_id,
            actor_id=actor.actor_id,
        )
    except RetentionError as error:
        raise _retention_error(error, payload.correlation_id) from error
    except Exception as error:
        raise _unavailable("retention_apply_unavailable", payload.correlation_id) from error
    request.state.audit_action = "operational_retention.apply"
    request.state.audit_resource_type = "operational_retention"
    request.state.audit_resource_id = payload.source_id
    request.state.audit_details = {
        "mode": receipt.mode,
        "outcome": receipt.outcome,
        "candidate_count": receipt.candidate_count,
        "deleted_count": receipt.deleted_count,
        "failed_count": receipt.failed_count,
        "deleted_logical_bytes": receipt.deleted_logical_bytes,
        "correlation_id": receipt.correlation_id,
    }
    return BaseResponse(
        data=RetentionReceiptView.model_validate(receipt, from_attributes=True),
        message="清理命令已完成 readback。",
    )


def _retention_error(error: RetentionError, correlation_id: str) -> HTTPException:
    statuses = {
        "validation": 422,
        "not_found": 404,
        "domain_blocked": 409,
        "conflict": 409,
        "idempotency_mismatch": 409,
        "unavailable": 503,
    }
    return typed_http_error(
        statuses.get(error.category, 500),
        error.category,
        error.code,
        error.message,
        correlation_id,
        retryable=error.retryable,
    )


def _unavailable(code: str, correlation_id: str = "operational-retention") -> HTTPException:
    return typed_http_error(
        503,
        "unavailable",
        code,
        "儲存空間資訊或清理服務暫時無法使用。",
        correlation_id,
        retryable=True,
    )


__all__ = ["router"]

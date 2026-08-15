"""
File: import_warning_tracking.py
Description: 提供管理員匯入警示追蹤的唯讀查詢與狀態 Preview／Apply API。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.import_warning_tracking import get_import_warning_tracking_application
from api.schemas.base import BaseResponse
from api.schemas.import_warning_tracking import ImportWarningTaskView, WarningTransitionBody, WarningTransitionPreviewView
from domains.anomalies.import_warning_tracking import ImportWarningTrackingStatus
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.anomalies.import_warning_tracking_workflow import ImportWarningTrackingApplication, WarningTransitionRequest


router = APIRouter(prefix="/api/v1/import-warning-tracking", tags=["Anomalies"])
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]


@router.get("/tasks", response_model=BaseResponse[list[ImportWarningTaskView]])
def query_tasks(active_only: bool = Query(True), limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0), principal: AdminPrincipal = Depends(require_system_admin), application: ImportWarningTrackingApplication = Depends(get_import_warning_tracking_application)):
    del principal
    return BaseResponse(data=[_task(item) for item in application.query_tasks(active_only=active_only, limit=limit, offset=offset)], message="成功取得匯入警示追蹤清單")


@router.post("/tasks/{occurrence_identity}/preview", response_model=BaseResponse[WarningTransitionPreviewView])
def preview_transition(body: WarningTransitionBody, occurrence_identity: str = Path(..., min_length=1, max_length=191), idempotency_key: _IdempotencyHeader = ..., correlation_id: _CorrelationHeader = ..., principal: AdminPrincipal = Depends(require_system_admin), application: ImportWarningTrackingApplication = Depends(get_import_warning_tracking_application)):
    return _transition(application.preview, body, occurrence_identity, idempotency_key, correlation_id, principal)


@router.post("/tasks/{occurrence_identity}/apply", response_model=BaseResponse[WarningTransitionPreviewView])
def apply_transition(body: WarningTransitionBody, occurrence_identity: str = Path(..., min_length=1, max_length=191), idempotency_key: _IdempotencyHeader = ..., correlation_id: _CorrelationHeader = ..., principal: AdminPrincipal = Depends(require_system_admin), application: ImportWarningTrackingApplication = Depends(get_import_warning_tracking_application)):
    return _transition(application.apply, body, occurrence_identity, idempotency_key, correlation_id, principal)


def _transition(operation, body, occurrence_identity, idempotency_key, correlation_id, principal):
    request = WarningTransitionRequest(occurrence_identity, body.expected_version, ImportWarningTrackingStatus(body.target_status), ActorContext(str(principal.username)), body.reason_code, body.note, body.evidence_reference, IdempotencyKey(idempotency_key), CorrelationId(correlation_id))
    try:
        result = operation(request)
    except ValueError as error:
        code = str(error)
        status = 404 if code == "import_warning_not_found" else 409 if code in {"import_warning_version_conflict", "import_warning_idempotency_mismatch"} else 422
        raise HTTPException(status_code=status, detail={"error": {"code": code, "correlation_id": correlation_id}}) from error
    return BaseResponse(data=_preview(result), message="匯入警示狀態已預覽" if operation.__name__ == "preview" else "匯入警示狀態已更新")


def _task(value):
    return {"occurrence_identity": value.occurrence_identity, "owning_lane": value.owning_lane, "logical_code": value.logical_code, "field_path": value.field_path, "masked_subject": value.masked_subject, "issue_codes": list(value.issue_codes), "tracking_status": value.tracking_status.value, "tracking_version": value.tracking_version, "evidence_reference": value.evidence_reference}


def _preview(value):
    return {"occurrence_identity": value.occurrence_identity, "expected_version": value.expected_version, "resulting_status": value.resulting_status.value, "resulting_version": value.resulting_version}


__all__ = ["router"]

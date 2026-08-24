"""
File: import_warning_tracking.py
Description: 提供匯入警示查詢、去敏 owner referral 與狀態 Preview／Apply API。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.import_warning_tracking import get_import_warning_tracking_application
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.import_warning_tracking import (
    ImportWarningTaskView,
    WarningReferralView,
    WarningTransitionBody,
    WarningTransitionPreviewView,
    WarningTransitionReceiptView,
)
from domains.anomalies.import_warning_tracking import ImportWarningTrackingStatus
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.anomalies.import_warning_tracking_workflow import ImportWarningTrackingApplication, WarningTransitionRequest


router = APIRouter(prefix="/api/v1/import-warning-tracking", tags=["Anomalies"])
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]
_ERROR_RESPONSES = {
    401: {"model": GlobalTypedErrorResponseView},
    403: {"model": GlobalTypedErrorResponseView},
    404: {"model": GlobalTypedErrorResponseView},
    409: {"model": GlobalTypedErrorResponseView},
    422: {"model": GlobalTypedErrorResponseView},
    500: {"model": GlobalTypedErrorResponseView},
    503: {"model": GlobalTypedErrorResponseView},
}


@router.get("/tasks", response_model=BaseResponse[list[ImportWarningTaskView]], responses=_ERROR_RESPONSES)
def query_tasks(active_only: bool = Query(True), limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0), principal: AdminPrincipal = Depends(require_system_admin), application: ImportWarningTrackingApplication = Depends(get_import_warning_tracking_application)):
    del principal
    return BaseResponse(data=[_task(item) for item in application.query_tasks(active_only=active_only, limit=limit, offset=offset)], message="成功取得匯入警示追蹤清單")


@router.get(
    "/tasks/{occurrence_identity}/referral",
    response_model=BaseResponse[WarningReferralView],
    responses=_ERROR_RESPONSES,
)
def query_referral(
    occurrence_identity: str = Path(..., min_length=1, max_length=191),
    expected_version: int = Query(..., ge=1),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ImportWarningTrackingApplication = Depends(
        get_import_warning_tracking_application
    ),
):
    del principal
    try:
        value = application.query_referral(
            occurrence_identity,
            expected_version=expected_version,
        )
    except ValueError as error:
        code = str(error)
        status = 404 if code == "import_warning_not_found" else 409 if code == "import_warning_version_conflict" else 422
        category = "not_found" if status == 404 else "conflict" if status == 409 else "domain_blocked"
        raise typed_http_error(status, category, code, _error_message(code), "import-warning-referral") from error
    return BaseResponse(
        data=_referral(value),
        message="成功取得匯入警示 owning 業面導向",
    )


@router.post("/tasks/{occurrence_identity}/preview", response_model=BaseResponse[WarningTransitionPreviewView], responses=_ERROR_RESPONSES)
def preview_transition(body: WarningTransitionBody, occurrence_identity: str = Path(..., min_length=1, max_length=191), idempotency_key: _IdempotencyHeader = ..., correlation_id: _CorrelationHeader = ..., principal: AdminPrincipal = Depends(require_system_admin), application: ImportWarningTrackingApplication = Depends(get_import_warning_tracking_application)):
    result = _transition(application.preview, body, occurrence_identity, idempotency_key, correlation_id, principal)
    return BaseResponse(data=_preview(result), message="匯入警示狀態已預覽")


@router.post("/tasks/{occurrence_identity}/apply", response_model=BaseResponse[WarningTransitionReceiptView], responses=_ERROR_RESPONSES)
def apply_transition(body: WarningTransitionBody, occurrence_identity: str = Path(..., min_length=1, max_length=191), idempotency_key: _IdempotencyHeader = ..., correlation_id: _CorrelationHeader = ..., principal: AdminPrincipal = Depends(require_system_admin), application: ImportWarningTrackingApplication = Depends(get_import_warning_tracking_application)):
    result = _transition(application.apply, body, occurrence_identity, idempotency_key, correlation_id, principal)
    return BaseResponse(data=_receipt(result), message="匯入警示狀態已更新")


@router.get("/receipts/{receipt_identity}", response_model=BaseResponse[WarningTransitionReceiptView], responses=_ERROR_RESPONSES)
def query_transition_receipt(receipt_identity: str = Path(..., pattern=r"^[0-9a-f]{64}$"), principal: AdminPrincipal = Depends(require_system_admin), application: ImportWarningTrackingApplication = Depends(get_import_warning_tracking_application)):
    del principal
    try:
        result = application.query_receipt(receipt_identity)
    except ValueError as error:
        code = str(error)
        status = 404 if code == "import_warning_receipt_not_found" else 500
        category = "not_found" if status == 404 else "internal"
        raise typed_http_error(status, category, code, _error_message(code), "import-warning-receipt-query") from error
    return BaseResponse(data=_receipt(result), message="成功取得匯入警示 transition receipt")


def _transition(operation, body, occurrence_identity, idempotency_key, correlation_id, principal):
    request = WarningTransitionRequest(occurrence_identity, body.expected_version, ImportWarningTrackingStatus(body.target_status), ActorContext(str(principal.username)), body.reason_code, body.note, body.evidence_reference, IdempotencyKey(idempotency_key), CorrelationId(correlation_id))
    try:
        result = operation(request)
    except ValueError as error:
        code = str(error)
        status = 404 if code == "import_warning_not_found" else 409 if code in {"import_warning_version_conflict", "import_warning_idempotency_mismatch"} else 422
        category = "not_found" if status == 404 else "idempotency_mismatch" if code == "import_warning_idempotency_mismatch" else "conflict" if status == 409 else "domain_blocked"
        raise typed_http_error(status, category, code, _error_message(code), correlation_id) from error
    return result


def _task(value):
    return {"occurrence_identity": value.occurrence_identity, "owning_lane": value.owning_lane, "logical_code": value.logical_code, "field_path": value.field_path, "masked_subject": value.masked_subject, "issue_codes": list(value.issue_codes), "tracking_status": value.tracking_status.value, "tracking_version": value.tracking_version, "evidence_reference": value.evidence_reference, "display_message": value.display_message, "navigation_action": value.navigation_action}


def _preview(value):
    return {"occurrence_identity": value.occurrence_identity, "expected_version": value.expected_version, "resulting_status": value.resulting_status.value, "resulting_version": value.resulting_version}


def _receipt(value):
    return {"occurrence_identity": value.occurrence_identity, "before_status": value.before_status.value, "after_status": value.after_status.value, "resulting_version": value.resulting_version, "receipt_identity": value.receipt_identity, "correlation_id": value.correlation_id, "replayed": value.replayed}


def _error_message(code: str) -> str:
    return {
        "import_warning_not_found": "找不到指定的匯入警示。",
        "import_warning_version_conflict": "匯入警示版本已變更，請重新查詢與預覽。",
        "import_warning_idempotency_mismatch": "冪等鍵與原始匯入警示指令不一致。",
        "import_warning_transition_not_allowed": "目前匯入警示狀態不允許此轉態。",
        "import_warning_receipt_not_found": "找不到指定的匯入警示 receipt。",
        "import_warning_receipt_invalid": "匯入警示 receipt 資料不符合契約。",
        "import_warning_referral_unavailable": "此警示尚未支援來源修復；可更新追蹤狀態，但不會修改來源根事實。",
    }.get(code, "匯入警示指令無法完成。")


def _referral(value):
    return {
        "occurrence_identity": value.occurrence_identity,
        "expected_version": value.expected_version,
        "owning_lane": value.owning_lane,
        "logical_code": value.logical_code,
        "field_path": value.field_path,
        "masked_subject": value.masked_subject,
        "display_message": value.display_message,
        "navigation_action": value.navigation_action,
        "action_kind": value.action_kind,
        "target_command": value.target_command,
    }


__all__ = ["router"]

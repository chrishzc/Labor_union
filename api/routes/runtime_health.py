"""
File: runtime_health.py
Description: 提供 runtime health 查詢與 LINE alert target typed 管理 API。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.error_contracts import typed_http_error
from api.dependencies.admin_auth import admin_actor_context, require_line_alert_manager, require_line_monitor_reader
from api.schemas.base import BaseResponse
from api.schemas.runtime_health import (
    AlertAdminCandidateResponse,
    AlertAdminTargetApplyRequest,
    AlertAdminTargetRequest,
    AlertTargetEnabledApplyRequest,
    AlertTargetEnabledRequest,
    AlertTargetMutationResponse,
    AlertTargetMutationPreviewResponse,
    AlertTargetViewResponse,
    ResetLineAlertGroupApplyRequest,
    ResetLineAlertGroupRequest,
    RuntimeHealthEventResponse,
    RuntimeHealthRecordResponse,
    SafeReviewLinkIssueRequest,
    SafeReviewLinkRedeemRequest,
    SafeReviewLinkRevokeRequest,
    SafeReviewLinkResponse,
    SafeReviewLinkReceiptResponse,
)
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.runtime_alert_target_application import RuntimeAlertTargetApplication
from subsystems.line.runtime_alert_target_contracts import (
    AddLineAlertAdminTargetCommand,
    ResetLineAlertGroupCommand,
    RuntimeAlertTargetError,
    SetLineAlertTargetEnabledCommand,
)
from subsystems.line.safe_review_link_application import SafeReviewLinkApplication
from subsystems.line.safe_review_link_contracts import (
    IssueSafeReviewLink,
    QuerySafeReviewLink,
    RedeemSafeReviewLink,
    RevokeSafeReviewLink,
    SafeReviewLinkError,
)

router = APIRouter(prefix="/api/v1/runtime", tags=["Runtime Health"])


def _safe_link_app() -> SafeReviewLinkApplication:
    return SafeReviewLinkApplication(open_line_unit_of_work, lambda: datetime.now(timezone.utc))


def _safe_link_view(view):
    return SafeReviewLinkResponse.model_validate(view, from_attributes=True)


def _safe_link_receipt(receipt):
    return SafeReviewLinkReceiptResponse(
        receipt_id=receipt.receipt_id,
        outcome=receipt.outcome.value,
        replayed=receipt.replayed,
        root_version=receipt.root_version,
        readback=_safe_link_view(receipt.view),
    )


def _safe_link_error(error: SafeReviewLinkError) -> HTTPException:
    mapping = {
        "safe_review_link_not_found": (404, "not_found", "safe_review_link_not_found"),
        "safe_review_link_wrong_actor": (403, "forbidden", "safe_review_link_wrong_actor"),
        "safe_review_link_expired": (410, "conflict", "safe_review_link_expired"),
        "safe_review_link_replayed": (409, "conflict", "safe_review_link_replayed"),
        "safe_review_link_revoked": (410, "conflict", "safe_review_link_revoked"),
        "safe_review_link_target_stale": (409, "conflict", "safe_review_link_target_stale"),
        "safe_review_link_version_conflict": (409, "conflict", "safe_review_link_version_conflict"),
        "safe_review_link_idempotency_mismatch": (409, "idempotency_mismatch", "safe_review_link_idempotency_mismatch"),
    }
    status, category, code = mapping.get(error.code, (422, "validation", "safe_review_link_invalid"))
    return typed_http_error(status, category, code, error.message, "safe-review-link", retryable=error.retryable)


@router.get("/line-safe-review-links/{link_id}", response_model=BaseResponse[SafeReviewLinkResponse])
def query_safe_review_link(link_id: str, _=Depends(require_line_monitor_reader)):
    try:
        return BaseResponse(data=_safe_link_view(_safe_link_app().query(QuerySafeReviewLink(link_id))))
    except SafeReviewLinkError as error:
        raise _safe_link_error(error) from error


@router.post("/line-safe-review-links", response_model=BaseResponse[SafeReviewLinkReceiptResponse])
def issue_safe_review_link(payload: SafeReviewLinkIssueRequest, principal=Depends(require_line_alert_manager)):
    actor = admin_actor_context(principal)
    try:
        receipt, _ = _safe_link_app().issue(IssueSafeReviewLink(
            payload.link_id, payload.raw_token, payload.canonical_internal_target,
            payload.target_version, payload.source_alert_identity, payload.allowed_actor_ref,
            payload.required_capability, payload.ttl_seconds, actor,
            IdempotencyKey(payload.idempotency_key), CorrelationId(payload.correlation_id),
        ))
        return BaseResponse(data=_safe_link_receipt(receipt))
    except SafeReviewLinkError as error:
        raise _safe_link_error(error) from error


@router.post("/line-safe-review-links/{link_id}/redeem", response_model=BaseResponse[SafeReviewLinkReceiptResponse])
def redeem_safe_review_link(link_id: str, payload: SafeReviewLinkRedeemRequest, principal=Depends(require_line_alert_manager)):
    actor = admin_actor_context(principal)
    try:
        receipt = _safe_link_app().redeem(RedeemSafeReviewLink(
            link_id, payload.raw_token, actor, payload.capability,
            payload.current_target, payload.current_target_version,
            IdempotencyKey(payload.idempotency_key), CorrelationId(payload.correlation_id),
        ))
        return BaseResponse(data=_safe_link_receipt(receipt))
    except SafeReviewLinkError as error:
        raise _safe_link_error(error) from error


@router.post("/line-safe-review-links/{link_id}/revoke", response_model=BaseResponse[SafeReviewLinkReceiptResponse])
def revoke_safe_review_link(link_id: str, payload: SafeReviewLinkRevokeRequest, principal=Depends(require_line_alert_manager)):
    actor = admin_actor_context(principal)
    try:
        receipt = _safe_link_app().revoke(RevokeSafeReviewLink(
            link_id, actor, payload.reason,
            IdempotencyKey(payload.idempotency_key), CorrelationId(payload.correlation_id),
        ))
        return BaseResponse(data=_safe_link_receipt(receipt))
    except SafeReviewLinkError as error:
        raise _safe_link_error(error) from error


@router.get("/health-status", response_model=list[RuntimeHealthRecordResponse])
def health_status(_=Depends(require_line_monitor_reader)):
    return [_record(item) for item in _query("list_status")]


@router.get("/health-events", response_model=list[RuntimeHealthEventResponse])
def health_events(limit: int = Query(100, ge=1, le=500), _=Depends(require_line_monitor_reader)):
    return [_event(item) for item in _query("list_events", limit)]


@router.get("/line-alert-targets", response_model=BaseResponse[list[AlertTargetViewResponse]])
def alert_targets(_=Depends(require_line_monitor_reader)):
    return BaseResponse(data=[AlertTargetViewResponse.model_validate(item, from_attributes=True) for item in _app().list_targets()])


@router.get("/line-alert-targets/admin-candidates", response_model=BaseResponse[list[AlertAdminCandidateResponse]])
def admin_alert_candidates(_=Depends(require_line_alert_manager)):
    return BaseResponse(data=[AlertAdminCandidateResponse.model_validate(item, from_attributes=True) for item in _app().list_admin_candidates()])


@router.post("/line-alert-targets/admin", response_model=BaseResponse[AlertTargetMutationResponse])
def add_admin_target(
    payload: AlertAdminTargetApplyRequest,
    request: Request,
    principal=Depends(require_line_alert_manager),
):
    actor = admin_actor_context(principal)
    try:
        result = _app().add_admin_target(AddLineAlertAdminTargetCommand(
            payload.admin_user_id,
            payload.minimum_status,
            payload.reason,
            IdempotencyKey(payload.idempotency_key),
            CorrelationId(payload.correlation_id),
            actor,
            PreviewFingerprint(payload.preview_fingerprint),
        ))
    except RuntimeAlertTargetError as error:
        raise _target_error(error, payload.correlation_id) from error
    _set_alert_target_audit(request, "enable", result.target_id)
    return BaseResponse(data=AlertTargetMutationResponse.model_validate(result, from_attributes=True))


@router.post("/line-alert-targets/admin/preview", response_model=BaseResponse[AlertTargetMutationPreviewResponse])
def preview_add_admin_target(
    payload: AlertAdminTargetRequest,
    principal=Depends(require_line_alert_manager),
):
    actor = admin_actor_context(principal)
    try:
        result = _app().preview(AddLineAlertAdminTargetCommand(
            payload.admin_user_id,
            payload.minimum_status,
            payload.reason,
            IdempotencyKey(payload.idempotency_key),
            CorrelationId(payload.correlation_id),
            actor,
        ))
    except RuntimeAlertTargetError as error:
        raise _target_error(error, payload.correlation_id) from error
    return BaseResponse(
        data=AlertTargetMutationPreviewResponse.model_validate(result, from_attributes=True),
        message="LINE 告警管理員對象 Preview 已建立；尚未寫入",
    )


@router.post("/line-alert-targets/group/reset", response_model=BaseResponse[AlertTargetMutationResponse])
def reset_group_target(
    payload: ResetLineAlertGroupApplyRequest,
    request: Request,
    principal=Depends(require_line_alert_manager),
):
    actor = admin_actor_context(principal)
    try:
        result = _app().reset(ResetLineAlertGroupCommand(
            payload.expected_version, payload.reason, IdempotencyKey(payload.idempotency_key),
            CorrelationId(payload.correlation_id), actor,
            PreviewFingerprint(payload.preview_fingerprint),
        ))
    except RuntimeAlertTargetError as error:
        raise _target_error(error, payload.correlation_id) from error
    _set_alert_target_audit(request, "group_reset", result.target_id)
    return BaseResponse(data=AlertTargetMutationResponse.model_validate(result, from_attributes=True))


@router.post("/line-alert-targets/group/reset/preview", response_model=BaseResponse[AlertTargetMutationPreviewResponse])
def preview_reset_group_target(
    payload: ResetLineAlertGroupRequest,
    principal=Depends(require_line_alert_manager),
):
    actor = admin_actor_context(principal)
    try:
        result = _app().preview(ResetLineAlertGroupCommand(
            payload.expected_version,
            payload.reason,
            IdempotencyKey(payload.idempotency_key),
            CorrelationId(payload.correlation_id),
            actor,
        ))
    except RuntimeAlertTargetError as error:
        raise _target_error(error, payload.correlation_id) from error
    return BaseResponse(
        data=AlertTargetMutationPreviewResponse.model_validate(result, from_attributes=True),
        message="LINE 告警群組重設 Preview 已建立；尚未寫入",
    )


@router.patch("/line-alert-targets/{target_id}", response_model=BaseResponse[AlertTargetMutationResponse])
def set_target_enabled(
    target_id: int,
    payload: AlertTargetEnabledApplyRequest,
    request: Request,
    principal=Depends(require_line_alert_manager),
):
    actor = admin_actor_context(principal)
    try:
        result = _app().set_enabled(SetLineAlertTargetEnabledCommand(
            target_id, payload.expected_version, payload.enabled, payload.reason,
            IdempotencyKey(payload.idempotency_key), CorrelationId(payload.correlation_id), actor,
            PreviewFingerprint(payload.preview_fingerprint),
        ))
    except RuntimeAlertTargetError as error:
        raise _target_error(error, payload.correlation_id) from error
    _set_alert_target_audit(request, "enable" if payload.enabled else "disable", target_id)
    return BaseResponse(data=AlertTargetMutationResponse.model_validate(result, from_attributes=True))


@router.post("/line-alert-targets/{target_id}/preview", response_model=BaseResponse[AlertTargetMutationPreviewResponse])
def preview_set_target_enabled(
    target_id: int,
    payload: AlertTargetEnabledRequest,
    principal=Depends(require_line_alert_manager),
):
    actor = admin_actor_context(principal)
    try:
        result = _app().preview(SetLineAlertTargetEnabledCommand(
            target_id,
            payload.expected_version,
            payload.enabled,
            payload.reason,
            IdempotencyKey(payload.idempotency_key),
            CorrelationId(payload.correlation_id),
            actor,
        ))
    except RuntimeAlertTargetError as error:
        raise _target_error(error, payload.correlation_id) from error
    return BaseResponse(
        data=AlertTargetMutationPreviewResponse.model_validate(result, from_attributes=True),
        message="LINE 告警對象狀態 Preview 已建立；尚未寫入",
    )


def _set_alert_target_audit(request: Request, action: str, target_id: int) -> None:
    request.state.audit_action = f"line.alert_target.{action}"
    request.state.audit_resource_type = "line_alert_target"
    request.state.audit_resource_id = str(target_id)


def _query(method, *args):
    connection = get_connection()
    try:
        return getattr(MySqlRuntimeMonitorRepository(connection), method)(*args)
    finally:
        connection.close()


def _app() -> RuntimeAlertTargetApplication:
    return RuntimeAlertTargetApplication(open_line_unit_of_work, lambda: datetime.now(timezone.utc))


def _target_error(error: RuntimeAlertTargetError, correlation_id: str) -> HTTPException:
    statuses = {"validation": 422, "not_found": 404, "conflict": 409, "idempotency_mismatch": 409, "unavailable": 503}
    return HTTPException(
        status_code=statuses.get(error.category, 500),
        detail={"error": {
            "category": error.category,
            "code": error.code,
            "message": error.message,
            "correlation_id": correlation_id,
            "field_errors": [],
            "domain_blockers": [],
            "retryable": error.retryable,
        }},
    )


def _record(item):
    return {name: getattr(item, name) for name in item.__dataclass_fields__}


def _event(item):
    return {name: getattr(item, name) for name in item.__dataclass_fields__}


__all__ = ["router"]

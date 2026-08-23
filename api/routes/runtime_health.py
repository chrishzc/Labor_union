"""
File: runtime_health.py
Description: 提供 runtime health 查詢與 LINE alert target typed 管理 API。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.dependencies.admin_auth import admin_actor_context, require_line_alert_manager, require_line_monitor_reader
from api.schemas.base import BaseResponse
from api.schemas.runtime_health import (
    AlertAdminCandidateResponse,
    AlertAdminTargetRequest,
    AlertTargetEnabledRequest,
    AlertTargetMutationResponse,
    AlertTargetViewResponse,
    ResetLineAlertGroupRequest,
    RuntimeHealthEventResponse,
    RuntimeHealthRecordResponse,
)
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.runtime_alert_target_application import RuntimeAlertTargetApplication
from subsystems.line.runtime_alert_target_contracts import (
    AddLineAlertAdminTargetCommand,
    ResetLineAlertGroupCommand,
    RuntimeAlertTargetError,
    SetLineAlertTargetEnabledCommand,
)

router = APIRouter(prefix="/api/v1/runtime", tags=["Runtime Health"])


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
    payload: AlertAdminTargetRequest,
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
        ))
    except RuntimeAlertTargetError as error:
        raise _target_error(error, payload.correlation_id) from error
    _set_alert_target_audit(request, "enable", result.target_id)
    return BaseResponse(data=AlertTargetMutationResponse.model_validate(result, from_attributes=True))


@router.post("/line-alert-targets/group/reset", response_model=BaseResponse[AlertTargetMutationResponse])
def reset_group_target(
    payload: ResetLineAlertGroupRequest,
    request: Request,
    principal=Depends(require_line_alert_manager),
):
    actor = admin_actor_context(principal)
    try:
        result = _app().reset(ResetLineAlertGroupCommand(
            payload.expected_version, payload.reason, IdempotencyKey(payload.idempotency_key),
            CorrelationId(payload.correlation_id), actor,
        ))
    except RuntimeAlertTargetError as error:
        raise _target_error(error, payload.correlation_id) from error
    _set_alert_target_audit(request, "group_reset", result.target_id)
    return BaseResponse(data=AlertTargetMutationResponse.model_validate(result, from_attributes=True))


@router.patch("/line-alert-targets/{target_id}", response_model=BaseResponse[AlertTargetMutationResponse])
def set_target_enabled(
    target_id: int,
    payload: AlertTargetEnabledRequest,
    request: Request,
    principal=Depends(require_line_alert_manager),
):
    actor = admin_actor_context(principal)
    try:
        result = _app().set_enabled(SetLineAlertTargetEnabledCommand(
            target_id, payload.expected_version, payload.enabled, payload.reason,
            IdempotencyKey(payload.idempotency_key), CorrelationId(payload.correlation_id), actor,
        ))
    except RuntimeAlertTargetError as error:
        raise _target_error(error, payload.correlation_id) from error
    _set_alert_target_audit(request, "enable" if payload.enabled else "disable", target_id)
    return BaseResponse(data=AlertTargetMutationResponse.model_validate(result, from_attributes=True))


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


def _mutate(method, *args):
    connection = get_connection()
    try:
        connection.begin()
        result = getattr(MySqlRuntimeMonitorRepository(connection), method)(*args)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _record(item):
    return {name: getattr(item, name) for name in item.__dataclass_fields__}


def _event(item):
    return {name: getattr(item, name) for name in item.__dataclass_fields__}


__all__ = ["router"]

"""
File: line_notification_rules.py
Description: 提供 LINE 通知規則矩陣、預覽、儲存啟用與安全刪除 API。
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_configuration_manager,
    require_line_configuration_reader,
)
from api.dependencies.line_runtime import (
    get_line_configuration_application,
    get_line_notification_rule_administration,
    get_line_notification_timeline_application,
    get_line_notification_manual_replay_application,
)
from api.schemas.base import BaseResponse
from api.schemas.line_notification_rules import (
    ApplyLineNotificationManualReplayRequest,
    DeleteLineNotificationRuleRequest,
    PreviewLineNotificationRulesRequest,
    SaveLineNotificationRulesRequest,
)
from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationRevisionConflict,
)
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(prefix="/api/v1/line/notification-rules", tags=["LINE Notification Rules"])


@router.get("", response_model=BaseResponse[dict])
def get_notification_rules(
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
):
    snapshot = get_line_configuration_application().get(
        LineConfigurationKind.NOTIFICATION_RULES,
        admin_actor_context(principal),
    )
    return BaseResponse(data={
        "revision": snapshot.revision.value,
        "definition": json.loads(snapshot.definition_json),
    })


@router.get("/timeline/{case_no}", response_model=BaseResponse[dict])
def get_notification_timeline(
    case_no: str,
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
):
    try:
        records = get_line_notification_timeline_application().list_case(
            case_no, admin_actor_context(principal)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return BaseResponse(data={"case_no": case_no, "records": list(records)})


@router.post("/sources/{source_event_id}/manual-replay/preview", response_model=BaseResponse[dict])
def preview_notification_manual_replay(
    source_event_id: int,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    try:
        result = get_line_notification_manual_replay_application().preview(
            source_event_id, admin_actor_context(principal)
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return BaseResponse(data=result)


@router.post("/sources/{source_event_id}/manual-replay", response_model=BaseResponse[dict])
def apply_notification_manual_replay(
    source_event_id: int,
    payload: ApplyLineNotificationManualReplayRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    try:
        replayed_source_id = get_line_notification_manual_replay_application().apply(
            source_event_id, admin_actor_context(principal), payload.reason,
            IdempotencyKey(payload.idempotency_key), CorrelationId(payload.correlation_id),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    request.state.audit_action = "line.notification_rule.manual_replay"
    request.state.audit_resource_type = "line_notification_source_event"
    request.state.audit_resource_id = str(source_event_id)
    return BaseResponse(data={"source_event_id": source_event_id, "replayed_source_event_id": replayed_source_id})


@router.post("/preview", response_model=BaseResponse[dict])
def preview_notification_rules(
    payload: PreviewLineNotificationRulesRequest,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    try:
        candidate = get_line_configuration_application().preview(
            LineConfigurationKind.NOTIFICATION_RULES,
            LineConfigurationRevision(payload.expected_revision),
            payload.definition,
            admin_actor_context(principal),
        )
    except (LineConfigurationRevisionConflict, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return BaseResponse(data={
        "before_revision": candidate.before_revision.value,
        "resulting_revision": candidate.resulting_revision.value,
        "definition": payload.definition,
        "fingerprint": candidate.fingerprint.value,
    })


@router.put("", response_model=BaseResponse[dict])
def save_notification_rules(
    payload: SaveLineNotificationRulesRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    try:
        result = get_line_configuration_application().apply(
            kind=LineConfigurationKind.NOTIFICATION_RULES,
            expected_revision=LineConfigurationRevision(payload.expected_revision),
            definition=payload.definition,
            actor=admin_actor_context(principal),
            reason=payload.reason,
            idempotency_key=IdempotencyKey(payload.idempotency_key),
            correlation_id=CorrelationId(payload.correlation_id),
        )
    except (LineConfigurationRevisionConflict, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    request.state.audit_action = "line.notification_rule.save"
    request.state.audit_resource_type = "line_notification_rules"
    request.state.audit_resource_id = "catalog"
    return BaseResponse(data={
        "revision": result.snapshot.revision.value,
        "definition": payload.definition,
    })


@router.delete("/{rule_id}", response_model=BaseResponse[dict])
def delete_notification_rule(
    rule_id: str,
    payload: DeleteLineNotificationRuleRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    application = get_line_notification_rule_administration()
    try:
        result = application.delete(
            rule_id=rule_id,
            expected_revision=LineConfigurationRevision(payload.expected_revision),
            actor=admin_actor_context(principal),
            reason=payload.reason,
            idempotency_key=IdempotencyKey(payload.idempotency_key),
            correlation_id=CorrelationId(payload.correlation_id),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (LineConfigurationRevisionConflict, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    request.state.audit_action = "line.notification_rule.delete"
    request.state.audit_resource_type = "line_notification_rule"
    request.state.audit_resource_id = rule_id
    return BaseResponse(data={
        "rule_id": rule_id,
        "revision": result.revision.value,
        "cancelled_intent_count": result.cancelled_intent_count,
    })


__all__ = ["router"]

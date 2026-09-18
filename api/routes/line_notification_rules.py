"""
File: line_notification_rules.py
Description: 提供 LINE 通知規則矩陣、預覽、儲存啟用與安全刪除 API。
"""

import json
from pathlib import Path
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pymysql.err import InterfaceError, OperationalError

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_configuration_manager,
    require_line_configuration_reader,
)
from api.error_contracts import typed_http_error
from api.dependencies.line_runtime import (
    get_line_configuration_application,
    get_line_notification_rule_administration,
    get_line_notification_timeline_application,
    get_line_notification_manual_replay_application,
)
from api.schemas.base import BaseResponse
from api.schemas.line_notification_rules import (
    ApplyLineNotificationManualReplayRequest,
    ApplyLineNotificationManualReplayView,
    DeleteLineNotificationRuleRequest,
    DeleteLineNotificationRuleView,
    LineNotificationRulesDefinition,
    LineNotificationRulesCatalogView,
    LineNotificationMessageTemplateView,
    LineNotificationTimelineView,
    PreviewLineNotificationRulesRequest,
    PreviewLineNotificationManualReplayView,
    PreviewLineNotificationRulesView,
    SaveLineNotificationRulesRequest,
    SaveLineNotificationRulesView,
    UpdateLineNotificationMessageTemplateRequest,
)
from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationRevisionConflict,
)
from domains.line.identities import LineConfigurationRevision
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_contracts import LineConfigurationQueryUnavailableError
from subsystems.line.notification_rule_administration import (
    LineNotificationRuleMutationError,
)
from subsystems.line.message_configuration import (
    LineMessageConfigurationError,
    validate_message_templates,
)


router = APIRouter(prefix="/api/v1/line/notification-rules", tags=["LINE Notification Rules"])
_TEMPLATE_VARIABLE = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}")


@router.get("", response_model=BaseResponse[LineNotificationRulesCatalogView])
def get_notification_rules(
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
):
    snapshot = get_line_configuration_application().get(
        LineConfigurationKind.NOTIFICATION_RULES,
        admin_actor_context(principal),
    )
    definition = _definition_from_snapshot(snapshot.definition_json)
    return BaseResponse(
        data=LineNotificationRulesCatalogView(
            revision=snapshot.revision.value,
            definition=definition,
        )
    )


@router.get(
    "/{rule_id}/message-template",
    response_model=BaseResponse[LineNotificationMessageTemplateView],
)
def get_notification_rule_message_template(
    rule_id: str,
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
):
    application = get_line_configuration_application()
    actor = admin_actor_context(principal)
    rule_snapshot = application.get(LineConfigurationKind.NOTIFICATION_RULES, actor)
    template_snapshot = application.get(LineConfigurationKind.MESSAGE_TEMPLATES, actor)
    return BaseResponse(data=_message_template_view(
        rule_id,
        _definition_from_snapshot(rule_snapshot.definition_json),
        _message_template_definition(template_snapshot),
        template_snapshot.revision.value,
    ))


@router.put(
    "/{rule_id}/message-template",
    response_model=BaseResponse[LineNotificationMessageTemplateView],
)
def update_notification_rule_message_template(
    rule_id: str,
    payload: UpdateLineNotificationMessageTemplateRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    application = get_line_configuration_application()
    actor = admin_actor_context(principal)
    rule_snapshot = application.get(LineConfigurationKind.NOTIFICATION_RULES, actor)
    template_snapshot = application.get(LineConfigurationKind.MESSAGE_TEMPLATES, actor)
    rules = _definition_from_snapshot(rule_snapshot.definition_json)
    definition = _message_template_definition(template_snapshot)
    view = _message_template_view(
        rule_id, rules, definition, template_snapshot.revision.value
    )
    template = next(
        item for item in definition["templates"]
        if item.get("id") == view.template_id
    )
    template["content"] = payload.content
    try:
        validate_message_templates(definition)
        result = application.apply(
            kind=LineConfigurationKind.MESSAGE_TEMPLATES,
            expected_revision=LineConfigurationRevision(payload.expected_revision),
            definition=definition,
            actor=actor,
            reason=payload.reason.strip(),
            idempotency_key=IdempotencyKey(
                f"line-notification-template:{rule_id}:{uuid4().hex[:12]}"
            ),
            correlation_id=CorrelationId(
                f"line-notification-template:{uuid4().hex[:12]}"
            ),
        )
    except LineConfigurationRevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail="通知訊息內容已遭修改，請重新載入後再試。",
        ) from error
    except LineMessageConfigurationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    request.state.audit_action = "line.notification_rule.message_template.update"
    request.state.audit_resource_type = "line_message_template"
    request.state.audit_resource_id = view.template_id
    return BaseResponse(
        data=_message_template_view(
            rule_id,
            rules,
            definition,
            result.snapshot.revision.value,
        ),
        message="通知訊息內容已成功儲存",
    )


@router.get("/timeline/{case_no}", response_model=BaseResponse[LineNotificationTimelineView])
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
    return BaseResponse(
        data=LineNotificationTimelineView(case_no=case_no, records=list(records))
    )


@router.post(
    "/sources/{source_event_id}/manual-replay/preview",
    response_model=BaseResponse[PreviewLineNotificationManualReplayView],
)
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
    return BaseResponse(data=PreviewLineNotificationManualReplayView.model_validate(result))


@router.post(
    "/sources/{source_event_id}/manual-replay",
    response_model=BaseResponse[ApplyLineNotificationManualReplayView],
)
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
    return BaseResponse(
        data=ApplyLineNotificationManualReplayView(
            source_event_id=source_event_id,
            replayed_source_event_id=replayed_source_id,
        )
    )


@router.post(
    "/preview",
    response_model=BaseResponse[PreviewLineNotificationRulesView],
)
def preview_notification_rules(
    payload: PreviewLineNotificationRulesRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    try:
        candidate = get_line_configuration_application().preview(
            LineConfigurationKind.NOTIFICATION_RULES,
            LineConfigurationRevision(payload.expected_revision),
            _definition_payload(payload.definition),
            admin_actor_context(principal),
        )
    except (
        LineConfigurationRevisionConflict,
        LineNotificationRuleMutationError,
        OperationalError,
        InterfaceError,
        ConnectionError,
        TimeoutError,
        RuntimeError,
        ValueError,
    ) as error:
        raise _rule_http_error(request, error) from error
    definition = LineNotificationRulesDefinition.model_validate(
        json.loads(candidate.definition_json)
    )
    return BaseResponse(
        data=PreviewLineNotificationRulesView(
            before_revision=candidate.before_revision.value,
            resulting_revision=candidate.resulting_revision.value,
            definition=definition,
            fingerprint=candidate.fingerprint.value,
        )
    )


@router.put("", response_model=BaseResponse[SaveLineNotificationRulesView])
def save_notification_rules(
    payload: SaveLineNotificationRulesRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    try:
        result = get_line_notification_rule_administration().save(
            definition=_definition_payload(payload.definition),
            expected_revision=LineConfigurationRevision(payload.expected_revision),
            preview_fingerprint=PreviewFingerprint(payload.preview_fingerprint),
            actor=admin_actor_context(principal),
            reason=payload.reason,
            idempotency_key=IdempotencyKey(payload.idempotency_key),
            correlation_id=CorrelationId(payload.correlation_id),
        )
    except (
        LineConfigurationRevisionConflict,
        LineNotificationRuleMutationError,
        OperationalError,
        InterfaceError,
        ConnectionError,
        TimeoutError,
        RuntimeError,
        ValueError,
    ) as error:
        raise _rule_http_error(request, error) from error
    request.state.audit_action = "line.notification_rule.save"
    request.state.audit_resource_type = "line_notification_rules"
    request.state.audit_resource_id = "catalog"
    return BaseResponse(
        data=SaveLineNotificationRulesView(
            revision=result.revision.value,
            preview_fingerprint=_fingerprint_value(result.preview_fingerprint),
            cancelled_intent_count=result.cancelled_intent_count,
            cancelled_task_count=result.cancelled_task_count,
        )
    )


@router.delete(
    "/{rule_id}",
    response_model=BaseResponse[DeleteLineNotificationRuleView],
)
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
            preview_fingerprint=PreviewFingerprint(payload.preview_fingerprint),
            actor=admin_actor_context(principal),
            reason=payload.reason,
            idempotency_key=IdempotencyKey(payload.idempotency_key),
            correlation_id=CorrelationId(payload.correlation_id),
        )
    except (
        LineConfigurationRevisionConflict,
        LineNotificationRuleMutationError,
        OperationalError,
        InterfaceError,
        ConnectionError,
        TimeoutError,
        RuntimeError,
        ValueError,
    ) as error:
        raise _rule_http_error(request, error) from error
    request.state.audit_action = "line.notification_rule.delete"
    request.state.audit_resource_type = "line_notification_rule"
    request.state.audit_resource_id = rule_id
    return BaseResponse(
        data=DeleteLineNotificationRuleView(
            rule_id=result.rule_id,
            revision=result.revision.value,
            preview_fingerprint=_fingerprint_value(result.preview_fingerprint),
            cancelled_intent_count=result.cancelled_intent_count,
            cancelled_task_count=result.cancelled_task_count,
        )
    )


def _definition_payload(definition: LineNotificationRulesDefinition) -> dict[str, object]:
    """Cross the HTTP boundary once with the closed schema's canonical JSON shape."""
    value = json.loads(definition.model_dump_json())
    if not isinstance(value, dict):
        raise ValueError("notification rule definition is invalid")
    return value


def _definition_from_snapshot(definition_json: str) -> LineNotificationRulesDefinition:
    value = json.loads(definition_json)
    if value == {}:
        value = {"rules": []}
    return LineNotificationRulesDefinition.model_validate(value)


def _message_template_definition(snapshot) -> dict[str, object]:
    if snapshot.revision.value == 0 or snapshot.definition_json == "{}":
        path = Path(__file__).resolve().parent.parent.parent / "config" / "message_templates.json"
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
        else:
            value = {"version": 1, "templates": []}
    else:
        value = json.loads(snapshot.definition_json)
    if not isinstance(value, dict) or not isinstance(value.get("templates"), list):
        raise HTTPException(status_code=409, detail="通知訊息設定目前無法讀取。")
    return value


def _message_template_view(
    rule_id: str,
    rules: LineNotificationRulesDefinition,
    templates_definition: dict[str, object],
    revision: int,
) -> LineNotificationMessageTemplateView:
    rule = next((item for item in rules.rules if item.id == rule_id), None)
    if rule is None:
        raise HTTPException(status_code=404, detail="找不到這筆通知規則。")
    templates = templates_definition.get("templates", [])
    template = next(
        (
            item for item in templates
            if isinstance(item, dict) and item.get("id") == rule.template_id
        ),
        None,
    )
    if template is None:
        raise HTTPException(status_code=404, detail="找不到此規則使用的訊息模板。")
    if template.get("message_type") != "text" or not isinstance(template.get("content"), str):
        raise HTTPException(status_code=409, detail="此規則使用的訊息格式目前不支援文字編輯。")
    variables = [
        str(item.get("name"))
        for item in template.get("variables", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    content = str(template["content"])
    sample_preview = _TEMPLATE_VARIABLE.sub(
        lambda match: f"〔{match.group(1)}〕",
        content,
    )
    return LineNotificationMessageTemplateView(
        rule_id=rule.id,
        template_id=rule.template_id,
        name=str(template.get("name") or rule.template_id),
        content=content,
        revision=revision,
        variables=variables,
        sample_preview=sample_preview,
    )


def _rule_http_error(request: Request, error: Exception) -> HTTPException:
    code = getattr(error, "code", None)
    if isinstance(error, LineNotificationRuleMutationError):
        status = 404 if code == "line_notification_rule_not_found" else 409
        category = "not_found" if status == 404 else "conflict"
        return typed_http_error(
            status,
            category,
            str(code),
            str(error),
            _request_correlation(request),
        )
    if isinstance(error, LineConfigurationRevisionConflict):
        return typed_http_error(
            409,
            "conflict",
            "line_notification_rule_revision_conflict",
            "LINE notification rule revision is stale",
            _request_correlation(request),
        )
    if isinstance(
        error,
        (
            LineConfigurationQueryUnavailableError,
            OperationalError,
            InterfaceError,
            ConnectionError,
            TimeoutError,
        ),
    ):
        return typed_http_error(
            503,
            "unavailable",
            "line_notification_rule_storage_unavailable",
            "LINE notification rule storage is temporarily unavailable",
            _request_correlation(request),
            retryable=True,
        )
    if isinstance(error, ValueError):
        return typed_http_error(
            422,
            "validation",
            "line_notification_rule_mutation_invalid",
            "LINE notification rule mutation request is invalid",
            _request_correlation(request),
        )
    return typed_http_error(
        500,
        "internal",
        "line_notification_rule_internal_error",
        "LINE notification rule mutation failed",
        _request_correlation(request),
    )


def _request_correlation(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    return value if isinstance(value, str) and value else "line-notification-rule-correlation-unavailable"


def _fingerprint_value(value: PreviewFingerprint | str) -> str:
    """Serialize the typed production value while keeping route doubles compatible."""
    if isinstance(value, PreviewFingerprint):
        return value.value
    if isinstance(value, str):
        return value
    raise TypeError("notification rule preview fingerprint is invalid")


__all__ = ["router"]

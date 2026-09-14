"""
File: line_onboarding.py
Description: 提供 LINE 新好友加入 Onboarding 歡迎訊息的查詢、預覽與手動編輯儲存 API。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_configuration_manager,
    require_line_configuration_reader,
)
from api.dependencies.line_runtime import get_line_configuration_application
from api.schemas.base import BaseResponse
from api.schemas.line_onboarding import (
    LineOnboardingView,
    PreviewLineOnboardingRequest,
    PreviewLineOnboardingView,
    UpdateLineOnboardingRequest,
)
from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationRevisionConflict,
)
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.message_configuration import (
    LineMessageConfigurationError,
    validate_message_templates,
)
from subsystems.line.webhook_identity_handlers import DEFAULT_ONBOARDING_WELCOME_MESSAGE

router = APIRouter(prefix="/api/v1/line/onboarding", tags=["LINE Onboarding"])

_SAMPLE_URL = "https://liff.line.me/{LIFF_ID}/gateway （安全專屬連結，15分鐘內有效）"


def _load_message_templates_definition(snapshot) -> dict[str, Any]:
    if snapshot.revision.value == 0 or snapshot.definition_json == "{}":
        path = Path(__file__).resolve().parent.parent.parent / "config" / "message_templates.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"version": 1, "templates": []}
    return json.loads(snapshot.definition_json)


def _get_onboarding_template_content(definition: dict[str, Any]) -> str:
    for t in definition.get("templates", []):
        if t.get("id") == "customer_onboarding_welcome" and isinstance(t.get("content"), str):
            return t["content"]
    return DEFAULT_ONBOARDING_WELCOME_MESSAGE


@router.get("", response_model=BaseResponse[LineOnboardingView])
def get_onboarding_message(
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
) -> BaseResponse[LineOnboardingView]:
    app = get_line_configuration_application()
    actor = admin_actor_context(principal)
    snapshot = app.get(LineConfigurationKind.MESSAGE_TEMPLATES, actor)
    definition = _load_message_templates_definition(snapshot)
    content = _get_onboarding_template_content(definition)
    sample_preview = content.replace("{url}", _SAMPLE_URL)
    return BaseResponse[LineOnboardingView](
        data=LineOnboardingView(
            template_id="customer_onboarding_welcome",
            content=content,
            revision=snapshot.revision.value,
            sample_preview=sample_preview,
            variables=["url"],
        )
    )


@router.post("/preview", response_model=BaseResponse[PreviewLineOnboardingView])
def preview_onboarding_message(
    payload: PreviewLineOnboardingRequest,
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
) -> BaseResponse[PreviewLineOnboardingView]:
    content = payload.content
    sample_preview = content.replace("{url}", _SAMPLE_URL)
    return BaseResponse[PreviewLineOnboardingView](
        data=PreviewLineOnboardingView(
            sample_preview=sample_preview,
            variables=["url"] if "{url}" in content else [],
        )
    )


@router.put("", response_model=BaseResponse[LineOnboardingView])
def update_onboarding_message(
    payload: UpdateLineOnboardingRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
) -> BaseResponse[LineOnboardingView]:
    app = get_line_configuration_application()
    actor = admin_actor_context(principal)
    snapshot = app.get(LineConfigurationKind.MESSAGE_TEMPLATES, actor)
    definition = _load_message_templates_definition(snapshot)

    templates = definition.setdefault("templates", [])
    found = False
    for t in templates:
        if t.get("id") == "customer_onboarding_welcome":
            t["content"] = payload.content
            t["enabled"] = True
            found = True
            break
    if not found:
        templates.insert(
            0,
            {
                "id": "customer_onboarding_welcome",
                "name": "新好友加入即時歡迎詞",
                "category": "webhook_reply",
                "message_type": "text",
                "enabled": True,
                "content": payload.content,
                "variables": [
                    {
                        "name": "url",
                        "required": True,
                        "description": "安全登記專屬連結",
                    }
                ],
                "usage": ["webhook"],
            },
        )

    try:
        validate_message_templates(definition)
    except LineMessageConfigurationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    idempotency_suffix = uuid4().hex[:12]
    try:
        result = app.apply(
            kind=LineConfigurationKind.MESSAGE_TEMPLATES,
            expected_revision=LineConfigurationRevision(payload.expected_revision),
            definition=definition,
            actor=actor,
            reason=payload.reason.strip(),
            idempotency_key=IdempotencyKey(
                f"line-onboarding-update:{payload.expected_revision}:{idempotency_suffix}"
            ),
            correlation_id=CorrelationId(f"line-onboarding:{uuid4().hex[:12]}"),
        )
    except LineConfigurationRevisionConflict as error:
        raise HTTPException(
            status_code=409, detail="歡迎訊息設定已遭修改，請重新整理後再試。"
        ) from error
    except Exception as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    request.state.audit_action = "line.onboarding.update"
    request.state.audit_resource_type = "line_configuration"
    request.state.audit_resource_id = "customer_onboarding_welcome"

    sample_preview = payload.content.replace("{url}", _SAMPLE_URL)
    return BaseResponse[LineOnboardingView](
        data=LineOnboardingView(
            template_id="customer_onboarding_welcome",
            content=payload.content,
            revision=result.snapshot.revision.value,
            sample_preview=sample_preview,
            variables=["url"],
        ),
        message="Onboarding 歡迎訊息已成功儲存",
    )

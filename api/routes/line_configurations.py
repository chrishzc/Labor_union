"""
================================================================================
檔案名稱: api/routes/line_configurations.py
功能說明: canonical LINE 訊息、排程、Rich Menu、LIFF 與客服設定版本 API
================================================================================
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_configuration_manager,
    require_line_configuration_reader,
)
from api.dependencies.line_runtime import get_line_configuration_application
from api.schemas.base import BaseResponse
from api.schemas.line_configurations import (
    ApplyLineConfigurationRequest,
    PreviewLineConfigurationRequest,
)
from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationRevisionConflict,
)
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.message_configuration import LineMessageConfigurationError

router = APIRouter(prefix="/api/v1/line/configurations", tags=["LINE Configuration"])


@router.get("/{kind}", response_model=BaseResponse[dict])
def get_configuration(
    kind: LineConfigurationKind,
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
):
    snapshot = get_line_configuration_application().get(
        kind,
        admin_actor_context(principal),
    )
    return BaseResponse(data=_snapshot(snapshot))


@router.post("/{kind}/preview", response_model=BaseResponse[dict])
def preview_configuration(
    kind: LineConfigurationKind,
    payload: PreviewLineConfigurationRequest,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    try:
        candidate = get_line_configuration_application().preview(
            kind,
            LineConfigurationRevision(payload.expected_revision),
            payload.definition,
            admin_actor_context(principal),
        )
    except (LineConfigurationRevisionConflict, LineMessageConfigurationError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return BaseResponse(
        data={
            "kind": candidate.kind.value,
            "before_revision": candidate.before_revision.value,
            "resulting_revision": candidate.resulting_revision.value,
            "definition": json.loads(candidate.definition_json),
            "fingerprint": candidate.fingerprint.value,
        }
    )


@router.put("/{kind}", response_model=BaseResponse[dict])
def apply_configuration(
    kind: LineConfigurationKind,
    payload: ApplyLineConfigurationRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
):
    try:
        result = get_line_configuration_application().apply(
            kind=kind,
            expected_revision=LineConfigurationRevision(payload.expected_revision),
            definition=payload.definition,
            actor=admin_actor_context(principal),
            reason=payload.reason.strip(),
            idempotency_key=IdempotencyKey(payload.idempotency_key),
            correlation_id=CorrelationId(payload.correlation_id),
        )
    except (LineConfigurationRevisionConflict, LineMessageConfigurationError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    request.state.audit_action = "line.configuration.apply"
    request.state.audit_resource_type = "line_configuration"
    request.state.audit_resource_id = kind.value
    return BaseResponse(data=_snapshot(result.snapshot), message="LINE 設定版本已套用")


def _snapshot(snapshot) -> dict[str, object]:
    return {
        "kind": snapshot.kind.value,
        "revision": snapshot.revision.value,
        "definition": json.loads(snapshot.definition_json),
    }


__all__ = ["router"]

"""
File: line_configurations.py
Description: 提供 LINE 設定安全查詢與通用 mutation，並封閉 Rich Menu 專用草稿旁路。
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
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.line_configurations import (
    ApplyLineConfigurationRequest,
    LineConfigurationPreviewView,
    LineConfigurationSafePublicView,
    LineConfigurationSafeResponse,
    LineConfigurationSnapshotView,
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
from subsystems.line.configuration_contracts import (
    GetLineConfigurationSafeQuery,
    LineConfigurationQueryContractError,
    LineConfigurationQueryUnavailableError,
)

router = APIRouter(prefix="/api/v1/line/configurations", tags=["LINE Configuration"])


@router.get("/{kind}/safe", response_model=LineConfigurationSafeResponse)
def get_safe_configuration(
    kind: LineConfigurationKind,
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
) -> LineConfigurationSafeResponse:
    try:
        result = get_line_configuration_application().get_safe(
            GetLineConfigurationSafeQuery(kind),
            admin_actor_context(principal),
        )
    except LineConfigurationQueryContractError as error:
        raise _safe_query_error(
            "line_configuration_query_contract_invalid",
            retryable=False,
        ) from error
    except LineConfigurationQueryUnavailableError as error:
        raise _safe_query_error(
            "line_configuration_query_unavailable",
            retryable=True,
        ) from error
    return LineConfigurationSafeResponse(
        data=LineConfigurationSafePublicView(
            kind=result.kind,
            revision=result.revision,
            state=result.state,
        )
    )


@router.get("/{kind}", response_model=BaseResponse[LineConfigurationSnapshotView])
def get_configuration(
    kind: LineConfigurationKind,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_reader),
) -> BaseResponse[LineConfigurationSnapshotView]:
    _require_dedicated_rich_menu_draft(kind, request)
    snapshot = get_line_configuration_application().get(
        kind,
        admin_actor_context(principal),
    )
    return BaseResponse[LineConfigurationSnapshotView](data=_snapshot(snapshot))


@router.post("/{kind}/preview", response_model=BaseResponse[LineConfigurationPreviewView])
def preview_configuration(
    kind: LineConfigurationKind,
    payload: PreviewLineConfigurationRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
) -> BaseResponse[LineConfigurationPreviewView]:
    _require_dedicated_rich_menu_draft(kind, request)
    try:
        candidate = get_line_configuration_application().preview(
            kind,
            LineConfigurationRevision(payload.expected_revision),
            payload.definition,
            admin_actor_context(principal),
        )
    except (LineConfigurationRevisionConflict, LineMessageConfigurationError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return BaseResponse[LineConfigurationPreviewView](
        data=LineConfigurationPreviewView(
            kind=candidate.kind,
            before_revision=candidate.before_revision.value,
            resulting_revision=candidate.resulting_revision.value,
            definition=json.loads(candidate.definition_json),
            fingerprint=candidate.fingerprint.value,
        )
    )


@router.put("/{kind}", response_model=BaseResponse[LineConfigurationSnapshotView])
def apply_configuration(
    kind: LineConfigurationKind,
    payload: ApplyLineConfigurationRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_configuration_manager),
) -> BaseResponse[LineConfigurationSnapshotView]:
    _require_dedicated_rich_menu_draft(kind, request)
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
    return BaseResponse[LineConfigurationSnapshotView](
        data=_snapshot(result.snapshot),
        message="LINE 設定版本已套用",
    )


def _snapshot(snapshot) -> LineConfigurationSnapshotView:
    return LineConfigurationSnapshotView(
        kind=snapshot.kind,
        revision=snapshot.revision.value,
        definition=json.loads(snapshot.definition_json),
    )


def _require_dedicated_rich_menu_draft(
    kind: LineConfigurationKind,
    request: Request,
) -> None:
    if kind is not LineConfigurationKind.RICH_MENUS:
        return
    correlation_id = getattr(
        request.state,
        "correlation_id",
        "line-rich-menu-draft-successor",
    )
    raise typed_http_error(
        410,
        "domain_blocked",
        "line_rich_menu_generic_configuration_retired",
        "Rich Menu 草稿不可使用通用設定端點；請改用專用 "
        "/api/v1/line/rich-menus/draft 契約。",
        correlation_id,
    )


def _safe_query_error(code: str, *, retryable: bool) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": {
                "category": "unavailable",
                "code": code,
                "message": "LINE 設定查詢結果無法安全提供。",
                "field_errors": [],
                "domain_blockers": [],
                "retryable": retryable,
                "correlation_id": "line-configuration-safe-query",
                "current_version": None,
            }
        },
    )


__all__ = ["router"]

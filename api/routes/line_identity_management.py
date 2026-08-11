"""Capability-protected administrative LINE identity management API."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_identity_binding_manager,
    require_line_identity_binding_override,
    require_line_identity_binding_reader,
)
from api.dependencies.line_runtime import publish_line_wakeup_best_effort
from api.schemas.base import BaseResponse
from api.schemas.line_identity_management import (
    LineIdentityBindingPageView,
    LineIdentityBindingView,
    LineIdentityRevocationActionRequest,
    LineIdentityRevocationApplyRequest,
    LineIdentityRevocationPreviewView,
    LineIdentityRevocationRequestView,
    LineIdentityReplacementPreviewView,
    LineIdentityReplacementRequest,
)
from domains.line.identities import LineUserId
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.identity_management_application import LineIdentityManagementApplication
from subsystems.line.identity_management_contracts import (
    LineIdentityBindingListQuery,
    RequestLineIdentityRevocationCommand,
    ReplaceLineIdentitySubjectCommand,
)


router = APIRouter(
    prefix="/api/v1/line/identity-bindings",
    tags=["LINE Identity Management"],
)


def _application() -> LineIdentityManagementApplication:
    return LineIdentityManagementApplication(
        open_line_unit_of_work,
        lambda: datetime.now(timezone.utc),
    )


@router.get("", response_model=BaseResponse[LineIdentityBindingPageView])
def list_bindings(
    status: LineIdentityBindingStatus | None = None,
    subject_type: LineBindingSubjectType | None = None,
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _: AdminPrincipal = Depends(require_line_identity_binding_reader),
):
    query = LineIdentityBindingListQuery(status, subject_type, search, page, page_size)
    return BaseResponse(data=_application().list(query))


@router.get("/{line_user_id}", response_model=BaseResponse[LineIdentityBindingView])
def binding_detail(
    line_user_id: str,
    _: AdminPrincipal = Depends(require_line_identity_binding_reader),
):
    return BaseResponse(data=_call(_application().detail, LineUserId(line_user_id)))


@router.post(
    "/{line_user_id}/replacement/preview",
    response_model=BaseResponse[LineIdentityReplacementPreviewView],
)
def preview_replacement(
    line_user_id: str,
    target_subject_reference: str,
    _: AdminPrincipal = Depends(require_line_identity_binding_manager),
):
    result = _call(
        _application().preview_replacement,
        LineUserId(line_user_id),
        target_subject_reference,
    )
    return BaseResponse(data=result)


@router.post(
    "/{line_user_id}/replacement/apply",
    response_model=BaseResponse[LineIdentityBindingView],
)
def apply_replacement(
    line_user_id: str,
    payload: LineIdentityReplacementRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_identity_binding_manager),
):
    command = ReplaceLineIdentitySubjectCommand(
        LineUserId(line_user_id),
        ExpectedVersion(payload.expected_version),
        payload.target_subject_reference,
        admin_actor_context(principal),
        payload.reason.strip(),
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
    )
    result = _call(_application().replace_subject, command)
    _audit_request(request, "replace", line_user_id)
    return BaseResponse(data=result, message="LINE 身分綁定對象已更正")


@router.post(
    "/{line_user_id}/revocation/preview",
    response_model=BaseResponse[LineIdentityRevocationPreviewView],
)
def preview_revocation(
    line_user_id: str,
    _: AdminPrincipal = Depends(require_line_identity_binding_manager),
):
    result = _call(_application().preview_revocation, LineUserId(line_user_id))
    return BaseResponse(data=result)


@router.post(
    "/{line_user_id}/revocation/apply",
    response_model=BaseResponse[LineIdentityRevocationRequestView],
)
def apply_revocation(
    line_user_id: str,
    payload: LineIdentityRevocationApplyRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_identity_binding_manager),
):
    command = RequestLineIdentityRevocationCommand(
        LineUserId(line_user_id),
        ExpectedVersion(payload.expected_version),
        admin_actor_context(principal),
        payload.reason.strip(),
        IdempotencyKey(payload.idempotency_key),
        CorrelationId(payload.correlation_id),
    )
    result = _call(_application().request_revocation, command)
    _audit_request(request, "request", line_user_id)
    publish_line_wakeup_best_effort()
    return BaseResponse(data=result, message="身分解除已排入 Rich Menu 回復流程")


@router.post(
    "/revocations/{request_id}/retry",
    response_model=BaseResponse[LineIdentityRevocationRequestView],
)
def retry_revocation(
    request_id: int,
    payload: LineIdentityRevocationActionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_identity_binding_manager),
):
    result = _call(
        _application().retry,
        request_id,
        admin_actor_context(principal),
        payload.reason.strip(),
    )
    _audit_request(request, "retry", str(request_id))
    publish_line_wakeup_best_effort()
    return BaseResponse(data=result, message="已重新排入 Rich Menu 回復流程")


@router.post(
    "/revocations/{request_id}/manual-complete",
    response_model=BaseResponse[LineIdentityRevocationRequestView],
)
def manual_complete_revocation(
    request_id: int,
    payload: LineIdentityRevocationActionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_line_identity_binding_override),
):
    result = _call(
        _application().finalize,
        request_id,
        manual_actor=admin_actor_context(principal),
        reason=payload.reason.strip(),
    )
    _audit_request(request, "manual_complete", str(request_id))
    return BaseResponse(data=result, message="身分已由 system admin 人工完成解除")


def _call(operation, *arguments, **keywords):
    try:
        return operation(*arguments, **keywords)
    except LookupError as error:
        raise HTTPException(status_code=404, detail={"code": str(error)}) from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail={"code": str(error)}) from error


def _audit_request(request: Request, action: str, resource_id: str) -> None:
    request.state.audit_action = f"line.identity.revocation.{action}"
    request.state.audit_resource_type = "line_identity_binding"
    request.state.audit_resource_id = resource_id


__all__ = ["router"]

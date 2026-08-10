"""System-admin commands for auditable, versioned capability grants."""

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies.admin_auth import require_system_admin
from api.schemas.base import BaseResponse
from api.schemas.capability_grants import CapabilityGrantApplyBody, CapabilityGrantReceiptView
from infrastructure.mysql.admin_capability_grant_repository import (
    CapabilityGrantCommand,
    CapabilityGrantError,
    apply_capability_grant,
    list_active_capability_grants,
)
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(prefix="/api/v1/admin/capability-grants", tags=["Capability Grants"])


@router.get("/{admin_user_id}", response_model=BaseResponse[list[dict]])
def list_grants(admin_user_id: int, _: AdminPrincipal = Depends(require_system_admin)):
    return BaseResponse(data=list_active_capability_grants(admin_user_id))


@router.post("/apply", response_model=BaseResponse[CapabilityGrantReceiptView])
def apply_grant(body: CapabilityGrantApplyBody, request: Request, actor: AdminPrincipal = Depends(require_system_admin)):
    try:
        receipt = apply_capability_grant(CapabilityGrantCommand(**body.model_dump()), actor)
    except CapabilityGrantError as error:
        raise HTTPException(status_code=_status_for(error.code), detail=error.code) from error
    request.state.audit_action = f"access.capability.{body.action}"
    request.state.audit_resource_type = "admin_capability_grant"
    request.state.audit_resource_id = str(body.target_admin_user_id)
    return BaseResponse(data=CapabilityGrantReceiptView(**receipt))


def _status_for(code: str) -> int:
    if code in {"admin_version_conflict", "idempotency_conflict", "last_system_admin_protected", "capability_grant_not_active"}:
        return 409
    if code in {"unknown_capability", "grant_command_invalid", "grant_expiry_required"}:
        return 422
    return 404 if code == "admin_user_not_active" else 403

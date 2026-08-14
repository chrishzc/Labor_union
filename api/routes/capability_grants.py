"""System-admin commands for auditable, versioned capability grants."""

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies.admin_auth import require_system_admin
from api.schemas.base import BaseResponse
from api.schemas.capability_grants import CapabilityGrantApplyBody, CapabilityGrantReceiptView
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(prefix="/api/v1/admin/capability-grants", tags=["Capability Grants"])


@router.get("/{admin_user_id}", response_model=BaseResponse[list[dict]])
def list_grants(admin_user_id: int, _: AdminPrincipal = Depends(require_system_admin)):
    del admin_user_id
    raise HTTPException(
        status_code=410,
        detail={
            "code": "capability_grants_retired",
            "replacement": "All authenticated enabled internal users have equal business access.",
        },
    )


@router.post("/apply", response_model=BaseResponse[CapabilityGrantReceiptView])
def apply_grant(
    body: CapabilityGrantApplyBody,
    request: Request,
    actor: AdminPrincipal = Depends(require_system_admin),
):
    del body, request, actor
    raise HTTPException(
        status_code=410,
        detail={
            "code": "capability_grants_retired",
            "replacement": "All authenticated enabled internal users have equal business access.",
        },
    )

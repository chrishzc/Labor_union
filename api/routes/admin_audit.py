"""Administrator audit queries; every valid administrator may inspect the safe view."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies.admin_auth import require_admin
from api.schemas.admin_audit import AdminAuditDetail, AdminAuditPage
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.access.security_audit_query import get_admin_audit_detail, list_admin_audits


router = APIRouter(prefix="/api/v1/admin/audits", tags=["Admin Audit"])


@router.get("", response_model=BaseResponse[AdminAuditPage])
def list_audits(
    action: str | None = None,
    actor_query: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _: AdminPrincipal = Depends(require_admin),
):
    result = list_admin_audits(page=page, page_size=page_size, action=action, actor_query=actor_query, created_from=created_from, created_to=created_to)
    return BaseResponse(data=AdminAuditPage(items=result.items, page=result.page, page_size=result.page_size, total=result.total, total_pages=max(1, (result.total + result.page_size - 1) // result.page_size)))


@router.get("/{audit_id}", response_model=BaseResponse[AdminAuditDetail])
def audit_detail(
    audit_id: int,
    _: AdminPrincipal = Depends(require_admin),
):
    detail = get_admin_audit_detail(audit_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="找不到管理員稽核紀錄")
    return BaseResponse(data=AdminAuditDetail(**detail))

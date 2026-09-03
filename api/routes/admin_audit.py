"""
File: admin_audit.py
Description: 提供管理員稽核清單唯讀查詢與受限 detail 相容入口。
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies.admin_auth import require_admin
from api.error_contracts import typed_http_error
from api.schemas.admin_audit import (
    AdminAuditDetailView,
    AdminAuditItemView,
    AdminAuditPageView,
)
from api.schemas.base import BaseResponse
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.access.security_audit_query import (
    AuditListItem,
    AuditQueryStorageError,
    get_admin_audit_detail,
    list_admin_audits,
)


router = APIRouter(prefix="/api/v1/admin/audits", tags=["Admin Audit"])


@router.get("", response_model=BaseResponse[AdminAuditPageView])
def list_audits(
    action: str | None = Query(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$"),
    action_prefix: str | None = Query(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$"),
    actor_query: str | None = Query(default=None, min_length=1, max_length=100),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _: AdminPrincipal = Depends(require_admin),
):
    if created_from is not None and created_to is not None and created_from > created_to:
        raise typed_http_error(422, "validation", "audit_date_range_invalid", "稽核查詢起日不得晚於迄日。", "access-audit-query")
    try:
        result = list_admin_audits(
            page=page,
            page_size=page_size,
            action=action,
            action_prefix=action_prefix,
            actor_query=actor_query,
            created_from=created_from,
            created_to=created_to,
            connection_factory=get_connection,
        )
    except AuditQueryStorageError as error:
        raise _audit_unavailable() from error
    total_pages = max(1, (result.total + result.page_size - 1) // result.page_size)
    return BaseResponse(
        data=AdminAuditPageView(
            items=[_item_view(item) for item in result.items],
            page=result.page,
            page_size=result.page_size,
            total=result.total,
            total_pages=total_pages,
        ),
        message="成功取得稽核清單",
    )


@router.get("/{audit_id}", response_model=BaseResponse[AdminAuditDetailView])
def audit_detail(
    audit_id: int,
    _: AdminPrincipal = Depends(require_admin),
):
    try:
        detail = get_admin_audit_detail(audit_id, connection_factory=get_connection)
    except AuditQueryStorageError as error:
        raise _audit_unavailable() from error
    if detail is None:
        raise typed_http_error(404, "not_found", "audit_record_not_found", "找不到管理員稽核紀錄。", "access-audit-query")
    return BaseResponse(data=AdminAuditDetailView.model_validate(asdict(detail)))


def _item_view(item: AuditListItem) -> AdminAuditItemView:
    return AdminAuditItemView.model_validate(asdict(item))


def _audit_unavailable() -> HTTPException:
    return typed_http_error(
        503,
        "unavailable",
        "audit_query_unavailable",
        "稽核查詢暫時無法使用。",
        "access-audit-query",
        retryable=True,
    )

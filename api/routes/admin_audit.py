"""Capability-protected privacy-safe administrator audit query API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.dependencies.admin_auth import require_line_audit_reader
from infrastructure.mysql.admin_audit_query_repository import (
    MySqlAdminAuditQueryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection


router = APIRouter(prefix="/api/v1/admin/audit", tags=["Admin Audit"])


@router.get("")
def list_admin_audit(
    action_prefix: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    _=Depends(require_line_audit_reader),
):
    connection = get_connection()
    try:
        return list(
            MySqlAdminAuditQueryRepository(connection).list(
                action_prefix=action_prefix,
                limit=limit,
            )
        )
    finally:
        connection.close()


__all__ = ["router"]

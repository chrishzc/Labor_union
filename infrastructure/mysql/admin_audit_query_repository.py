"""Privacy-safe read adapter for administrator operation audit records."""

from __future__ import annotations


class MySqlAdminAuditQueryRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def list(self, *, action_prefix: str | None, limit: int) -> tuple[dict, ...]:
        pattern = f"{action_prefix.strip()}%" if action_prefix else "%"
        with self._connection.cursor() as cursor:
            cursor.execute(_LIST_AUDIT, (pattern, limit))
            rows = cursor.fetchall() or ()
        return tuple(_safe_record(row) for row in rows)


def _safe_record(row) -> dict:
    return {
        "id": int(row["id"]),
        "actor": row.get("display_name") or "系統／未知人員",
        "action": str(row["action"]),
        "resource_type": row.get("resource_type"),
        "resource_id": row.get("resource_id"),
        "request_path": row.get("request_path"),
        "http_method": row.get("http_method"),
        "result_status": row.get("result_status"),
        "created_at": row.get("created_at"),
    }


_LIST_AUDIT = """SELECT a.id,u.display_name,a.action,a.resource_type,a.resource_id,
a.request_path,a.http_method,a.result_status,a.created_at
FROM admin_audit_logs a LEFT JOIN admin_users u ON u.id=a.admin_user_id
WHERE a.action LIKE %s ORDER BY a.created_at DESC,a.id DESC LIMIT %s"""


__all__ = ["MySqlAdminAuditQueryRepository"]

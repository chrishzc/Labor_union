"""Safe administration audit queries and the bounded retention mover."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pymysql

from infrastructure.mysql.mysql_adapter import get_connection


ONLINE_RETENTION_YEARS = 2
SENSITIVE_DETAIL_KEYS = frozenset({"password", "token", "authorization", "line_user_id", "phone", "identity_number"})


@dataclass(frozen=True)
class AuditPage:
    items: list[dict[str, Any]]
    page: int
    page_size: int
    total: int


def mask_audit_details(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "***" if key.lower() in SENSITIVE_DETAIL_KEYS else mask_audit_details(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_audit_details(item) for item in value]
    return value


def mask_ip_address(ip_address: str | None) -> str | None:
    if not ip_address:
        return None
    parts = ip_address.split(".")
    return ".".join([*parts[:3], "***"]) if len(parts) == 4 else "***"


def list_admin_audits(*, page: int, page_size: int, action: str | None, actor_query: str | None, created_from: datetime | None, created_to: datetime | None) -> AuditPage:
    clauses, params = _audit_filters(action, actor_query, created_from, created_to)
    where_sql = " AND ".join(clauses)
    with get_connection() as connection:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM admin_audit_logs a LEFT JOIN admin_users u ON u.id=a.admin_user_id WHERE {where_sql}", params)
            total = int((cursor.fetchone() or {}).get("total") or 0)
            cursor.execute(_audit_list_sql(where_sql), [*params, page_size, (page - 1) * page_size])
            rows = list(cursor.fetchall())
    return AuditPage([_audit_list_item(row) for row in rows], page, page_size, total)


def get_admin_audit_detail(audit_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(_audit_detail_sql(), (audit_id,))
            row = cursor.fetchone()
    return _audit_detail_item(row) if row else None


def archive_expired_admin_audits(*, batch_size: int = 500) -> int:
    with get_connection() as connection:
        try:
            connection.begin()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(_expired_audit_select_sql(), (batch_size,))
                rows = list(cursor.fetchall())
                _archive_audit_rows(cursor, rows)
            connection.commit()
            return len(rows)
        except Exception:
            connection.rollback()
            raise


def _audit_filters(action, actor_query, created_from, created_to):
    clauses, params = ["1=1"], []
    if action:
        clauses.append("a.action=%s"); params.append(action)
    if actor_query:
        clauses.append("(u.username LIKE %s OR u.display_name LIKE %s)"); params.extend([f"%{actor_query.strip()}%"] * 2)
    if created_from:
        clauses.append("a.created_at >= %s"); params.append(created_from)
    if created_to:
        clauses.append("a.created_at <= %s"); params.append(created_to)
    return clauses, params


def _audit_list_sql(where_sql: str) -> str:
    return f"SELECT a.id,a.admin_user_id,a.action,a.resource_type,a.resource_id,a.request_path,a.http_method,a.result_status,a.ip_address,a.created_at,u.display_name AS actor_display_name FROM admin_audit_logs a LEFT JOIN admin_users u ON u.id=a.admin_user_id WHERE {where_sql} ORDER BY a.created_at DESC,a.id DESC LIMIT %s OFFSET %s"


def _audit_detail_sql() -> str:
    return "SELECT a.*,u.display_name AS actor_display_name FROM admin_audit_logs a LEFT JOIN admin_users u ON u.id=a.admin_user_id WHERE a.id=%s"


def _audit_list_item(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["ip_address_masked"] = mask_ip_address(result.pop("ip_address", None))
    return result


def _audit_detail_item(row: dict[str, Any]) -> dict[str, Any]:
    result = _audit_list_item(row)
    raw_details = result.pop("details_json", None)
    result["details"] = mask_audit_details(json.loads(raw_details) if isinstance(raw_details, str) else raw_details)
    return result


def _expired_audit_select_sql() -> str:
    return "SELECT * FROM admin_audit_logs WHERE created_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 2 YEAR) ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"


def _archive_audit_rows(cursor: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cursor.executemany("INSERT IGNORE INTO admin_audit_log_archive (source_audit_id,admin_user_id,action,resource_type,resource_id,request_path,http_method,result_status,ip_address,details_json,created_at) VALUES (%(id)s,%(admin_user_id)s,%(action)s,%(resource_type)s,%(resource_id)s,%(request_path)s,%(http_method)s,%(result_status)s,%(ip_address)s,%(details_json)s,%(created_at)s)", rows)
    cursor.execute(f"DELETE FROM admin_audit_logs WHERE id IN ({','.join(['%s'] * len(rows))})", [row["id"] for row in rows])

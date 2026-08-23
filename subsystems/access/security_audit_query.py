"""
File: security_audit_query.py
Description: 執行安全稽核查詢、遮罩投影與既有保留期搬移。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import pymysql

from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import TAIPEI_TIME_ZONE


ONLINE_RETENTION_YEARS = 2
SENSITIVE_DETAIL_KEYS = frozenset({"password", "token", "authorization", "line_user_id", "phone", "identity_number"})


@dataclass(frozen=True)
class AuditListItem:
    audit_id: int
    occurred_at: datetime
    actor_label_masked: str | None
    action_family: Literal["authentication", "account_security", "session", "mfa", "system", "other"]
    target_label_masked: str | None
    ip_address_masked: str | None
    outcome: Literal["success", "denied", "failed", "unknown"]
    reason_code: str | None


@dataclass(frozen=True)
class AuditDetailField:
    key: Literal["reason", "mfa_method", "account", "enabled", "source", "subject"]
    value_masked: str


@dataclass(frozen=True)
class AuditDetailItem(AuditListItem):
    details: tuple[AuditDetailField, ...]


@dataclass(frozen=True)
class AuditPage:
    items: list[AuditListItem]
    page: int
    page_size: int
    total: int


def project_masked_audit_page(page: AuditPage) -> list[AuditListItem]:
    """將儲存層稽核列收斂為不含 raw details 的 UI 公開投影。"""
    return list(page.items)


def _mask_label(value: object) -> str | None:
    if value is None:
        return None
    label = str(value).strip()
    if not label:
        return None
    return f"{label[:1]}***"


def _mask_target(resource_type: object, resource_id: object) -> str | None:
    kind = str(resource_type).strip() if resource_type is not None else ""
    identity = str(resource_id).strip() if resource_id is not None else ""
    if not kind and not identity:
        return None
    if identity:
        return f"{kind or 'resource'}:{identity[:2]}***"
    return kind[:100]


def _action_family(action: str) -> str:
    normalized = action.lower()
    if normalized.startswith("admin.login"):
        return "authentication"
    if normalized.startswith("admin.account"):
        return "account_security"
    if normalized.startswith("admin.session") or "session" in normalized:
        return "session"
    if normalized.startswith("admin.mfa") or "totp" in normalized:
        return "mfa"
    if normalized.startswith("admin.system") or normalized.startswith("system."):
        return "system"
    return "other"


def _audit_outcome(result_status: object) -> Literal["success", "denied", "failed", "unknown"]:
    if result_status is None:
        return "unknown"
    try:
        status = int(result_status)
    except (TypeError, ValueError):
        return "unknown"
    if 200 <= status < 400:
        return "success"
    if status in {401, 403}:
        return "denied"
    if status >= 400:
        return "failed"
    return "unknown"


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


def list_admin_audits(*, page: int, page_size: int, action: str | None, action_prefix: str | None = None, actor_query: str | None, created_from: datetime | None, created_to: datetime | None) -> AuditPage:
    clauses, params = _audit_filters(
        action, action_prefix, actor_query, created_from, created_to
    )
    where_sql = " AND ".join(clauses)
    try:
        with get_connection() as connection:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(f"SELECT COUNT(*) AS total FROM admin_audit_logs a LEFT JOIN admin_users u ON u.id=a.admin_user_id WHERE {where_sql}", params)
                total = int((cursor.fetchone() or {}).get("total") or 0)
                cursor.execute(_audit_list_sql(where_sql), [*params, page_size, (page - 1) * page_size])
                rows = list(cursor.fetchall())
    except pymysql.MySQLError as error:
        raise AuditQueryStorageError("audit query storage unavailable") from error
    return AuditPage([_audit_list_item(row) for row in rows], page, page_size, total)


def get_admin_audit_detail(audit_id: int) -> AuditDetailItem | None:
    try:
        with get_connection() as connection:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(_audit_detail_sql(), (audit_id,))
                row = cursor.fetchone()
    except pymysql.MySQLError as error:
        raise AuditQueryStorageError("audit detail storage unavailable") from error
    return _audit_detail_item(row) if row else None


class AuditQueryStorageError(RuntimeError):
    pass


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


def _audit_filters(action, action_prefix, actor_query, created_from, created_to):
    clauses, params = ["1=1"], []
    if action:
        clauses.append("a.action=%s"); params.append(action)
    if action_prefix:
        clauses.append("a.action LIKE %s"); params.append(f"{action_prefix.strip()}%")
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


def _audit_list_item(row: dict[str, Any]) -> AuditListItem:
    action = str(row.get("action") or "")
    return AuditListItem(
        audit_id=int(row["id"]),
        occurred_at=_as_business_datetime(row["created_at"]),
        actor_label_masked=_mask_label(row.get("actor_display_name")),
        action_family=_action_family(action),
        target_label_masked=_mask_target(row.get("resource_type"), row.get("resource_id")),
        ip_address_masked=mask_ip_address(row.get("ip_address")),
        outcome=_audit_outcome(row.get("result_status")),
        reason_code=action if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", action) else None,
    )


def _as_business_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("audit timestamp must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=TAIPEI_TIME_ZONE)
    return value.astimezone(TAIPEI_TIME_ZONE)


def _audit_detail_item(row: dict[str, Any]) -> AuditDetailItem:
    item = _audit_list_item(row)
    raw_details = row.get("details_json")
    if isinstance(raw_details, str):
        try:
            raw_details = json.loads(raw_details)
        except json.JSONDecodeError:
            raw_details = None
    return AuditDetailItem(
        **item.__dict__,
        details=tuple(_safe_detail_fields(raw_details)),
    )


def _safe_detail_fields(value: object) -> list[AuditDetailField]:
    if not isinstance(value, dict):
        return []
    fields: list[AuditDetailField] = []
    if "reason" in value:
        fields.append(AuditDetailField("reason", "provided"))
    if "mfa_method" in value:
        method = value.get("mfa_method")
        fields.append(AuditDetailField("mfa_method", method if method in {"totp", "recovery_code"} else "other"))
    if "account_id" in value:
        fields.append(AuditDetailField("account", _mask_target("account", value.get("account_id")) or "account"))
    if isinstance(value.get("enabled"), bool):
        fields.append(AuditDetailField("enabled", "enabled" if value["enabled"] else "disabled"))
    if "source" in value:
        fields.append(AuditDetailField("source", "recorded"))
    if "subject_hash" in value:
        fields.append(AuditDetailField("subject", "recorded"))
    return fields


def _expired_audit_select_sql() -> str:
    return "SELECT * FROM admin_audit_logs WHERE created_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 2 YEAR) ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"


def _archive_audit_rows(cursor: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cursor.executemany("INSERT IGNORE INTO admin_audit_log_archive (source_audit_id,admin_user_id,action,resource_type,resource_id,request_path,http_method,result_status,ip_address,details_json,created_at) VALUES (%(id)s,%(admin_user_id)s,%(action)s,%(resource_type)s,%(resource_id)s,%(request_path)s,%(http_method)s,%(result_status)s,%(ip_address)s,%(details_json)s,%(created_at)s)", rows)
    cursor.execute(f"DELETE FROM admin_audit_logs WHERE id IN ({','.join(['%s'] * len(rows))})", [row["id"] for row in rows])

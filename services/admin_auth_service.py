"""Database-backed administrator authentication and audit helpers."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pymysql

from services.db_service import get_connection


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
ROLE_LEVELS = {
    "line_viewer": 10,
    "line_agent": 20,
    "line_manager": 30,
    "system_admin": 40,
}


@dataclass(frozen=True)
class AdminPrincipal:
    id: int | None
    username: str
    display_name: str
    role: str
    linked_line_user_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "linked_line_user_id": self.linked_line_user_id,
        }


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_admin_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("管理員密碼至少需要 12 個字元")
    salt = os.urandom(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
    )
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(derived).decode("ascii"),
        ]
    )


def verify_admin_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, expected_b64 = encoded_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_b64.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, binascii.Error):
        return False


def create_admin_user(
    *,
    username: str,
    password: str,
    display_name: str,
    role: str = "system_admin",
    linked_line_user_id: str | None = None,
) -> int:
    username = username.strip().lower()
    display_name = display_name.strip()
    if not username or not display_name:
        raise ValueError("username 與 display_name 不可為空")
    if role not in ROLE_LEVELS:
        raise ValueError(f"不支援的管理員角色：{role}")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO admin_users (
                    username, password_hash, display_name, linked_line_user_id, role
                ) VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    username,
                    hash_admin_password(password),
                    display_name,
                    linked_line_user_id or None,
                    role,
                ),
            )
            admin_id = int(cursor.lastrowid)
        conn.commit()
        return admin_id
    except pymysql.err.IntegrityError as exc:
        conn.rollback()
        raise ValueError("管理員帳號或綁定的 LINE 使用者已存在") from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def authenticate_admin(
    username: str,
    password: str,
    *,
    session_minutes: int,
) -> tuple[str, datetime, AdminPrincipal] | None:
    username = username.strip().lower()
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, username, password_hash, display_name, role,
                       linked_line_user_id, enabled
                FROM admin_users
                WHERE username=%s
                FOR UPDATE
                """,
                (username,),
            )
            row = cursor.fetchone()
            if not row or not row["enabled"] or not verify_admin_password(password, row["password_hash"]):
                conn.rollback()
                return None

            now = _utc_now_naive()
            expires_at = now + timedelta(minutes=max(5, min(session_minutes, 1440)))
            token = secrets.token_urlsafe(48)
            cursor.execute(
                """
                INSERT INTO admin_sessions (
                    admin_user_id, session_token_hash, expires_at, last_seen_at
                ) VALUES (%s,%s,%s,%s)
                """,
                (row["id"], _token_hash(token), expires_at, now),
            )
            cursor.execute(
                "UPDATE admin_users SET last_login_at=%s WHERE id=%s",
                (now, row["id"]),
            )
        conn.commit()
        return token, expires_at, AdminPrincipal(
            id=int(row["id"]),
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
            linked_line_user_id=row.get("linked_line_user_id"),
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_admin_session(token: str) -> AdminPrincipal | None:
    if not token:
        return None
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT u.id, u.username, u.display_name, u.role,
                       u.linked_line_user_id
                FROM admin_sessions s
                JOIN admin_users u ON u.id=s.admin_user_id
                WHERE s.session_token_hash=%s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > UTC_TIMESTAMP()
                  AND u.enabled=TRUE
                LIMIT 1
                """,
                (_token_hash(token),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            cursor.execute(
                "UPDATE admin_sessions SET last_seen_at=UTC_TIMESTAMP() WHERE session_token_hash=%s",
                (_token_hash(token),),
            )
        conn.commit()
        return AdminPrincipal(
            id=int(row["id"]),
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
            linked_line_user_id=row.get("linked_line_user_id"),
        )
    finally:
        conn.close()


def revoke_admin_session(token: str) -> bool:
    if not token:
        return False
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE admin_sessions
                SET revoked_at=COALESCE(revoked_at,UTC_TIMESTAMP())
                WHERE session_token_hash=%s
                """,
                (_token_hash(token),),
            )
            changed = cursor.rowcount > 0
        conn.commit()
        return changed
    finally:
        conn.close()


def renew_admin_session(token: str, *, session_minutes: int) -> datetime | None:
    """Extend a valid session without exposing or replacing its stored hash."""
    if not token:
        return None
    expires_at = _utc_now_naive() + timedelta(
        minutes=max(5, min(session_minutes, 1440))
    )
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE admin_sessions s
                JOIN admin_users u ON u.id=s.admin_user_id
                SET s.expires_at=%s, s.last_seen_at=UTC_TIMESTAMP()
                WHERE s.session_token_hash=%s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > UTC_TIMESTAMP()
                  AND u.enabled=TRUE
                """,
                (expires_at, _token_hash(token)),
            )
            renewed = cursor.rowcount > 0
        conn.commit()
        return expires_at if renewed else None
    finally:
        conn.close()


def has_required_role(principal: AdminPrincipal, minimum_role: str) -> bool:
    return ROLE_LEVELS.get(principal.role, 0) >= ROLE_LEVELS.get(minimum_role, 10**9)


def record_admin_audit(
    *,
    principal: AdminPrincipal | None,
    action: str,
    request_path: str | None = None,
    http_method: str | None = None,
    result_status: int | None = None,
    ip_address: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO admin_audit_logs (
                    admin_user_id, action, resource_type, resource_id,
                    request_path, http_method, result_status, ip_address,
                    details_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    principal.id if principal and principal.id is not None else None,
                    action,
                    resource_type,
                    resource_id,
                    request_path,
                    http_method,
                    result_status,
                    ip_address,
                    json.dumps(details, ensure_ascii=False) if details else None,
                ),
            )
        conn.commit()
    finally:
        conn.close()

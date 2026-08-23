"""
File: authentication_session.py
Description: 管理後台帳號、Session、root 身分與多因素登入的資料庫安全編排。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pymysql

from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.access.security_audit_query import mask_audit_details
from subsystems.access.totp import (
    EncryptedTotpSecret,
    TotpError,
    TotpSecretUnavailableError,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    provisioning_uri,
    totp_cipher_from_environment,
    verify_recovery_code,
    verify_totp,
)


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
ADMIN_SESSION_IDLE_MINUTES = 30
ADMIN_SESSION_MAXIMUM_MINUTES = 8 * 60
LOGIN_ATTEMPT_WINDOW_MINUTES = 15
LOGIN_ATTEMPT_MAXIMUM = 5
SECURITY_ALERT_ACTION_CODES = {
    "admin.root.bootstrap": "access_root_bootstrapped",
    "admin.account.created": "access_account_created",
    "admin.account.enabled_changed": "access_account_state_changed",
    "admin.account.password_reset": "access_password_reset",
    "admin.account.sessions_revoked": "access_sessions_revoked",
    "admin.account.mfa_reset": "access_mfa_reset",
    "admin.login.disabled_account": "access_disabled_account_usage",
    "admin.mfa.enrollment_issued": "access_mfa_enrollment_issued",
    "admin.mfa.enrollment_completed": "access_mfa_enrollment_completed",
    "admin.login.rate_limited": "access_login_rate_limited",
    "admin.login.mfa_replay": "access_mfa_replay",
}
REQUIRED_ADMIN_SESSION_COLUMNS = frozenset(
    {
        "admin_user_id",
        "session_token_hash",
        "expires_at",
        "absolute_expires_at",
        "last_seen_at",
        "revoked_at",
    }
)


class AdminLoginRateLimitedError(Exception):
    """登入主體在固定時間窗內的失敗次數已達上限。"""


class AdminMfaReplayError(Exception):
    """已成功使用過的 TOTP time-step 不能再次換取 Session。"""
ROLE_LEVELS = {
    "line_viewer": 10,
    "line_agent": 20,
    "line_manager": 30,
    "system_admin": 40,
}
CAPABILITY_REGISTRY = frozenset(
    {
        "line.identity.read",
        "line.identity.review",
        "line.review.read",
        "line.review.decide",
        "line.task.read",
        "line.task.control",
        "line.task.retry",
        "line.task.cancel",
        "line.task.send",
        "line.menu.publish",
        "line.config.read",
        "line.config.manage",
        "line.rich_menu.publish",
        "line.identity.bind_admin",
        "line.identity.review_staff",
        "line.order_group.read",
        "line.order_group.bind",
        "line.monitor.read",
        "line.alert.manage",
        "line.audit.read",
        "line.matching.read",
        "line.matching.send",
        "line.matching.override",
        "line.customer_service.read",
        "line.customer_service.handle",
        "line.identity.binding.read",
        "line.identity.binding.manage",
        "line.identity.binding.override",
        "contract.evidence.read",
        "contract.evidence.manage",
        "knowledge.read",
        "knowledge.manage",
        "knowledge.publish",
        "knowledge.reindex",
        "integration.event.read",
        "integration.event.retry",
        "admin.user.manage",
        "admin.session.revoke",
        "admin.audit.read",
        "data_browser.read",
        "data_browser.write",
        "system.configuration.manage",
        "system.administration",
        "knowledge.source.edit",
        "knowledge.source.review",
        "knowledge.source.publish",
        "knowledge.answer.query",
    }
)
ROLE_CAPABILITIES = {
    role: CAPABILITY_REGISTRY
    for role in ROLE_LEVELS
}


class AdminSessionSchemaError(RuntimeError):
    """Raised when the preserved database lacks the governed session schema."""


class AdminSessionStorageError(RuntimeError):
    """Raised when administrator session storage is temporarily unavailable."""


class AdminMfaConfigurationError(RuntimeError):
    """Raised when a required MFA factor cannot be used safely."""


@dataclass(frozen=True)
class MfaEnrollmentChallenge:
    """One-time enrollment proof returned only after a successful password check."""

    challenge_id: str
    challenge_token: str
    provisioning_uri: str
    expires_at: datetime


@dataclass(frozen=True)
class PasswordLoginChallenge:
    """Password proof that cannot itself authorize a business Session."""

    challenge_id: str
    challenge_token: str
    expires_at: datetime


@dataclass(frozen=True)
class AdminPrincipal:
    id: int | None
    username: str
    display_name: str
    role: str
    linked_line_user_id: str | None = None
    capabilities: frozenset[str] | None = None
    is_root: bool = False
    enabled: bool = True
    access_control_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "linked_line_user_id": self.linked_line_user_id,
            "capabilities": sorted(self.effective_capabilities()),
            "is_root": self.is_root,
            "enabled": self.enabled,
            "access_control_version": self.access_control_version,
        }

    def effective_capabilities(self) -> frozenset[str]:
        if self.id is None and self.capabilities is not None:
            return self.capabilities & CAPABILITY_REGISTRY
        return ROLE_CAPABILITIES.get(self.role, frozenset())


@dataclass(frozen=True)
class AccountCommandReceipt:
    """Safe, stable result of one Account Center mutation command."""

    operation: str
    target_account_id: int
    resulting_access_control_version: int
    receipt_identity: str
    replayed: bool


@dataclass(frozen=True)
class AccountCreationResult:
    account: AdminPrincipal
    receipt: AccountCommandReceipt


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _session_expiry(now: datetime, absolute_expires_at: datetime) -> datetime:
    return min(
        now + timedelta(minutes=ADMIN_SESSION_IDLE_MINUTES), absolute_expires_at
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _attempt_subject_hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


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


def bootstrap_root_admin(
    *, username: str, password: str, display_name: str, linked_line_user_id: str | None = None
) -> int:
    """Offline-only initial root bootstrap; it fails closed once a root fact exists."""
    normalized_username = username.strip().lower()
    normalized_name = display_name.strip()
    if not normalized_username or not normalized_name:
        raise ValueError("username 與 display_name 不可為空")
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cursor:
            cursor.execute("SELECT admin_user_id FROM admin_root_account WHERE singleton_key=1 FOR UPDATE")
            if cursor.fetchone() is not None:
                raise ValueError("root 帳號已存在；不得以 bootstrap 覆寫")
            cursor.execute(
                """INSERT INTO admin_users (
                    username, password_hash, display_name, linked_line_user_id, role
                ) VALUES (%s,%s,%s,%s,'system_admin')""",
                (normalized_username, hash_admin_password(password), normalized_name, linked_line_user_id or None),
            )
            admin_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO admin_root_account (singleton_key,admin_user_id) VALUES (1,%s)",
                (admin_id,),
            )
            _record_admin_audit_with_cursor(
                cursor, principal=None, action="admin.root.bootstrap", result_status=201,
                details={"account_id": admin_id},
            )
        conn.commit()
        return admin_id
    except pymysql.err.IntegrityError as error:
        conn.rollback()
        raise ValueError("root bootstrap 衝突") from error
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_account_center_users() -> list[AdminPrincipal]:
    """Return account metadata only; encrypted factors and password hashes never leave storage."""
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """SELECT u.id, u.username, u.display_name, u.role, u.linked_line_user_id, u.enabled,
                   u.access_control_version,
                   EXISTS(SELECT 1 FROM admin_root_account r WHERE r.admin_user_id=u.id) AS is_root
                   FROM admin_users u ORDER BY u.username"""
            )
            return [_principal_from_row(cursor, row) for row in cursor.fetchall()]
    except pymysql.MySQLError as error:
        raise AdminSessionStorageError("帳號中心儲存服務暫時無法使用") from error
    finally:
        conn.close()


def create_account_center_user_with_receipt(
    *, actor: AdminPrincipal, username: str, password: str, display_name: str,
    linked_line_user_id: str | None = None, reason: str, idempotency_key: str,
) -> AccountCreationResult:
    """Create or safely replay an enabled equal-business account creation command."""
    _require_root_actor(actor, reason)
    normalized_username = username.strip().lower()
    normalized_name = display_name.strip()
    if not normalized_username or not normalized_name:
        raise ValueError("username 與 display_name 不可為空")
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            command_payload = {
                "username": normalized_username,
                "password_hash": _token_hash(password),
                "display_name": normalized_name,
                "linked_line_user_id": linked_line_user_id or None,
            }
            replayed = _replay_account_create(
                cursor, idempotency_key, actor, reason, command_payload
            )
            if replayed is not None:
                conn.commit()
                return AccountCreationResult(
                    replayed,
                    _account_command_receipt(
                        "account-create", idempotency_key, int(replayed.id or 0), 1, replayed=True,
                    ),
                )
            cursor.execute(
                """INSERT INTO admin_users (username,password_hash,display_name,linked_line_user_id,role)
                VALUES (%s,%s,%s,%s,'system_admin')""",
                (normalized_username, hash_admin_password(password), normalized_name, linked_line_user_id or None),
            )
            account_id = int(cursor.lastrowid)
            principal = AdminPrincipal(account_id, normalized_username, normalized_name, "system_admin")
            _record_admin_audit_with_cursor(
                cursor, principal=actor, action="admin.account.created", result_status=201,
                details={"account_id": account_id, "reason": reason.strip()},
            )
            _save_account_command_receipt(
                cursor, "account-create", idempotency_key, actor, 0, 1, reason, command_payload,
                result_snapshot={
                    "id": account_id, "username": normalized_username,
                    "display_name": normalized_name, "role": "system_admin",
                    "access_control_version": 1,
                },
            )
        conn.commit()
        return AccountCreationResult(
            principal,
            _account_command_receipt(
                "account-create", idempotency_key, account_id, 1, replayed=False,
            ),
        )
    except pymysql.err.IntegrityError as error:
        conn.rollback()
        raise ValueError("管理員帳號或綁定的 LINE 使用者已存在") from error
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_account_center_user(
    *, actor: AdminPrincipal, username: str, password: str, display_name: str,
    linked_line_user_id: str | None = None, reason: str, idempotency_key: str,
) -> AdminPrincipal:
    """Compatibility entry returning the created account while the API exposes its receipt."""
    return create_account_center_user_with_receipt(
        actor=actor,
        username=username,
        password=password,
        display_name=display_name,
        linked_line_user_id=linked_line_user_id,
        reason=reason,
        idempotency_key=idempotency_key,
    ).account


def set_account_center_enabled(*, actor: AdminPrincipal, account_id: int, enabled: bool, reason: str, expected_version: int, idempotency_key: str) -> AccountCommandReceipt:
    """Enable or disable a non-root account and revoke sessions in the same transaction."""
    _require_root_account_action(actor, account_id, reason)
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if _replay_account_command(cursor, "account-enabled", idempotency_key, actor, account_id, expected_version, reason, {"enabled": enabled}):
                conn.commit()
                return _account_command_receipt("account-enabled", idempotency_key, account_id, expected_version + 1, replayed=True)
            _lock_non_root_account(cursor, account_id, expected_version)
            cursor.execute("UPDATE admin_users SET enabled=%s, access_control_version=access_control_version+1 WHERE id=%s", (enabled, account_id))
            if not enabled:
                cursor.execute(
                    "UPDATE admin_sessions SET revoked_at=COALESCE(revoked_at,UTC_TIMESTAMP(6)) WHERE admin_user_id=%s",
                    (account_id,),
                )
            _record_admin_audit_with_cursor(
                cursor, principal=actor, action="admin.account.enabled_changed", result_status=200,
                details={"account_id": account_id, "enabled": enabled, "reason": reason.strip()},
            )
            _save_account_command_receipt(cursor, "account-enabled", idempotency_key, actor, account_id, expected_version, reason, {"enabled": enabled})
        conn.commit()
        return _account_command_receipt("account-enabled", idempotency_key, account_id, expected_version + 1, replayed=False)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset_account_center_password(*, actor: AdminPrincipal, account_id: int, password: str, reason: str, expected_version: int, idempotency_key: str) -> AccountCommandReceipt:
    """Set a new password and revoke all existing sessions atomically."""
    _require_root_account_action(actor, account_id, reason)
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            payload = {"password_hash": _token_hash(password)}
            if _replay_account_command(cursor, "account-password-reset", idempotency_key, actor, account_id, expected_version, reason, payload):
                conn.commit()
                return _account_command_receipt("account-password-reset", idempotency_key, account_id, expected_version + 1, replayed=True)
            _lock_non_root_account(cursor, account_id, expected_version)
            cursor.execute("UPDATE admin_users SET password_hash=%s, access_control_version=access_control_version+1 WHERE id=%s", (hash_admin_password(password), account_id))
            cursor.execute(
                "UPDATE admin_sessions SET revoked_at=COALESCE(revoked_at,UTC_TIMESTAMP(6)) WHERE admin_user_id=%s",
                (account_id,),
            )
            _record_admin_audit_with_cursor(
                cursor, principal=actor, action="admin.account.password_reset", result_status=200,
                details={"account_id": account_id, "reason": reason.strip()},
            )
            _save_account_command_receipt(cursor, "account-password-reset", idempotency_key, actor, account_id, expected_version, reason, payload)
        conn.commit()
        return _account_command_receipt("account-password-reset", idempotency_key, account_id, expected_version + 1, replayed=False)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def revoke_account_center_sessions(*, actor: AdminPrincipal, account_id: int, reason: str, expected_version: int, idempotency_key: str) -> AccountCommandReceipt:
    """Revoke all sessions for a selected account with an auditable operator reason."""
    _require_root_account_action(actor, account_id, reason)
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if _replay_account_command(cursor, "account-sessions-revoke", idempotency_key, actor, account_id, expected_version, reason, {}):
                conn.commit()
                return _account_command_receipt("account-sessions-revoke", idempotency_key, account_id, expected_version + 1, replayed=True)
            _lock_non_root_account(cursor, account_id, expected_version)
            cursor.execute("UPDATE admin_users SET access_control_version=access_control_version+1 WHERE id=%s", (account_id,))
            cursor.execute(
                "UPDATE admin_sessions SET revoked_at=COALESCE(revoked_at,UTC_TIMESTAMP(6)) WHERE admin_user_id=%s",
                (account_id,),
            )
            _record_admin_audit_with_cursor(
                cursor, principal=actor, action="admin.account.sessions_revoked", result_status=200,
                details={"account_id": account_id, "reason": reason.strip()},
            )
            _save_account_command_receipt(cursor, "account-sessions-revoke", idempotency_key, actor, account_id, expected_version, reason, {})
        conn.commit()
        return _account_command_receipt("account-sessions-revoke", idempotency_key, account_id, expected_version + 1, replayed=False)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset_account_center_mfa(*, actor: AdminPrincipal, account_id: int, reason: str, expected_version: int, idempotency_key: str) -> AccountCommandReceipt:
    """Revoke a non-root factor and its sessions; the user must enroll again after password proof."""
    _require_root_account_action(actor, account_id, reason)
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if _replay_account_command(cursor, "account-mfa-reset", idempotency_key, actor, account_id, expected_version, reason, {}):
                conn.commit()
                return _account_command_receipt("account-mfa-reset", idempotency_key, account_id, expected_version + 1, replayed=True)
            _lock_non_root_account(cursor, account_id, expected_version)
            cursor.execute("UPDATE admin_users SET access_control_version=access_control_version+1 WHERE id=%s", (account_id,))
            cursor.execute(
                """UPDATE admin_totp_factors SET factor_state='revoked', revoked_at=UTC_TIMESTAMP(6)
                WHERE admin_user_id=%s AND factor_state IN ('active','enrollment_pending')""",
                (account_id,),
            )
            cursor.execute(
                "UPDATE admin_sessions SET revoked_at=COALESCE(revoked_at,UTC_TIMESTAMP(6)) WHERE admin_user_id=%s",
                (account_id,),
            )
            _record_admin_audit_with_cursor(
                cursor, principal=actor, action="admin.account.mfa_reset", result_status=200,
                details={"account_id": account_id, "reason": reason.strip()},
            )
            _save_account_command_receipt(cursor, "account-mfa-reset", idempotency_key, actor, account_id, expected_version, reason, {})
        conn.commit()
        return _account_command_receipt("account-mfa-reset", idempotency_key, account_id, expected_version + 1, replayed=False)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _require_root_account_action(actor: AdminPrincipal, account_id: int, reason: str) -> None:
    _require_root_actor(actor, reason)
    if account_id <= 0:
        raise ValueError("帳號不存在")


def _require_root_actor(actor: AdminPrincipal, reason: str) -> None:
    """Require the sole account-center operator and an accountable reason."""
    if not actor.is_root:
        raise PermissionError("僅 root 可管理帳號")
    if not reason.strip():
        raise ValueError("高風險帳號操作必須提供原因")


def _lock_non_root_account(cursor: Any, account_id: int, expected_version: int) -> None:
    cursor.execute("SELECT id, access_control_version FROM admin_users WHERE id=%s FOR UPDATE", (account_id,))
    account = cursor.fetchone()
    if account is None:
        raise ValueError("帳號不存在")
    actual_version = int(account["access_control_version"])
    if actual_version != expected_version:
        raise ValueError("admin_version_conflict")
    cursor.execute("SELECT 1 FROM admin_root_account WHERE admin_user_id=%s", (account_id,))
    if cursor.fetchone() is not None:
        raise ValueError("root 帳號受保護，必須走離線維運程序")


def _account_command_fingerprint(
    *, actor: AdminPrincipal, account_id: int, expected_version: int, reason: str, payload: dict[str, Any]
) -> str:
    canonical = json.dumps(
        {"actor_id": actor.id, "account_id": account_id, "expected_version": expected_version,
         "reason": reason.strip(), "payload": payload},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _account_command_receipt(
    operation: str,
    idempotency_key: str,
    target_account_id: int,
    resulting_access_control_version: int,
    *,
    replayed: bool,
) -> AccountCommandReceipt:
    receipt_identity = hashlib.sha256(
        f"account-command-receipt:v1:{operation}:{idempotency_key}".encode("utf-8")
    ).hexdigest()
    return AccountCommandReceipt(
        operation=operation,
        target_account_id=target_account_id,
        resulting_access_control_version=resulting_access_control_version,
        receipt_identity=receipt_identity,
        replayed=replayed,
    )


def _replay_account_command(
    cursor: Any, family: str, idempotency_key: str, actor: AdminPrincipal,
    account_id: int, expected_version: int, reason: str, payload: dict[str, Any],
) -> bool:
    fingerprint = _account_command_fingerprint(
        actor=actor, account_id=account_id, expected_version=expected_version, reason=reason, payload=payload
    )
    cursor.execute(
        "SELECT request_fingerprint FROM admin_command_receipts "
        "WHERE command_family=%s AND idempotency_key=%s FOR UPDATE",
        (family, idempotency_key),
    )
    row = cursor.fetchone()
    if row is None:
        return False
    stored = str(row["request_fingerprint"] if isinstance(row, dict) else row[0])
    if not hmac.compare_digest(stored, fingerprint):
        raise ValueError("idempotency_key_conflict")
    return True


def _replay_account_create(
    cursor: Any, idempotency_key: str, actor: AdminPrincipal, reason: str, payload: dict[str, Any],
) -> AdminPrincipal | None:
    """Return the original safe account view when a create command is replayed."""
    fingerprint = _account_command_fingerprint(
        actor=actor, account_id=0, expected_version=1, reason=reason, payload=payload
    )
    cursor.execute(
        "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
        "WHERE command_family=%s AND idempotency_key=%s FOR UPDATE",
        ("account-create", idempotency_key),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    stored = str(row["request_fingerprint"] if isinstance(row, dict) else row[0])
    if not hmac.compare_digest(stored, fingerprint):
        raise ValueError("idempotency_key_conflict")
    snapshot = row.get("result_snapshot") if isinstance(row, dict) else row[1]
    try:
        result = json.loads(str(snapshot))
        account_id = int(result["id"])
        username = str(result["username"])
        display_name = str(result["display_name"])
        role = str(result["role"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AdminSessionStorageError("帳號建立 receipt 已損毀") from error
    return AdminPrincipal(account_id, username, display_name, role)


def _save_account_command_receipt(
    cursor: Any, family: str, idempotency_key: str, actor: AdminPrincipal,
    account_id: int, expected_version: int, reason: str, payload: dict[str, Any],
    result_snapshot: dict[str, Any] | None = None,
) -> None:
    fingerprint = _account_command_fingerprint(
        actor=actor, account_id=account_id, expected_version=expected_version, reason=reason, payload=payload
    )
    cursor.execute(
        """INSERT INTO admin_command_receipts (
            command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (family, idempotency_key, fingerprint, fingerprint, str(actor.id), reason.strip(),
         json.dumps(result_snapshot or {"account_id": account_id, "applied": True}, ensure_ascii=False)),
    )


def authenticate_admin(
    username: str,
    password: str,
    *,
    session_minutes: int,
    totp_code: str | None = None,
    source_identifier: str = "unknown",
) -> tuple[str, datetime, AdminPrincipal] | None:
    username = username.strip().lower()
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            _require_admin_session_schema(cursor)
            cursor.execute(
                """
                SELECT u.id, u.username, u.password_hash, u.display_name, u.role,
                       u.linked_line_user_id, u.enabled, u.access_control_version,
                       EXISTS(SELECT 1 FROM admin_root_account r
                              WHERE r.admin_user_id=u.id) AS is_root
                FROM admin_users u
                WHERE username=%s
                FOR UPDATE
                """,
                (username,),
            )
            row = cursor.fetchone()
            if _is_rate_limited(cursor, username, source_identifier):
                _record_login_attempt(cursor, username, source_identifier, "rate_limited")
                conn.commit()
                raise AdminLoginRateLimitedError()
            if not row or not row["enabled"] or not verify_admin_password(password, row["password_hash"]):
                _record_login_attempt(cursor, username, source_identifier, "failed")
                if row is not None and not row["enabled"]:
                    _record_disabled_account_login_attempt(cursor, username)
                conn.commit()
                return None

            factor = _active_factor_for_user(cursor, int(row["id"]))
            if factor is None:
                enrollment = _issue_mfa_enrollment(cursor, row)
                _record_login_attempt(cursor, username, source_identifier, "succeeded")
                _record_admin_audit_with_cursor(
                    cursor, principal=_principal_from_row(cursor, row),
                    action="admin.mfa.enrollment_issued", result_status=403,
                )
                conn.commit()
                return enrollment
            if not totp_code:
                _record_login_attempt(cursor, username, source_identifier, "failed")
                conn.commit()
                return None
            try:
                verification = _verify_and_consume_second_factor(cursor, factor, totp_code)
            except AdminMfaReplayError:
                _record_login_attempt(cursor, username, source_identifier, "mfa_replay")
                conn.commit()
                return None
            if not verification:
                _record_login_attempt(cursor, username, source_identifier, "failed")
                conn.commit()
                return None

            now = _utc_now_naive()
            del session_minutes
            absolute_expires_at = now + timedelta(minutes=ADMIN_SESSION_MAXIMUM_MINUTES)
            expires_at = _session_expiry(now, absolute_expires_at)
            token = secrets.token_urlsafe(48)
            cursor.execute(
                """
                INSERT INTO admin_sessions (
                    admin_user_id, session_token_hash, expires_at, absolute_expires_at,
                    last_seen_at
                ) VALUES (%s,%s,%s,%s,%s)
                """,
                (row["id"], _token_hash(token), expires_at, absolute_expires_at, now),
            )
            cursor.execute(
                "UPDATE admin_users SET last_login_at=%s WHERE id=%s",
                (now, row["id"]),
            )
            principal = _principal_from_row(cursor, row)
            _record_admin_audit_with_cursor(
                cursor,
                principal=principal,
                action="admin.login.success",
                result_status=200,
                details={"mfa_method": verification},
            )
            _record_login_attempt(cursor, username, source_identifier, "succeeded")
        conn.commit()
        return token, expires_at, principal
    except (AdminSessionSchemaError, AdminMfaConfigurationError):
        conn.rollback()
        raise
    except pymysql.MySQLError as error:
        conn.rollback()
        raise AdminSessionStorageError("管理員登入儲存服務暫時無法使用") from error
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def issue_password_login_challenge(
    username: str, password: str, *, source_identifier: str = "unknown",
) -> PasswordLoginChallenge | MfaEnrollmentChallenge | None:
    """Verify only the password and persist a short-lived second-factor challenge."""
    normalized_username = username.strip().lower()
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            _require_admin_session_schema(cursor)
            cursor.execute(
                """SELECT u.id, u.username, u.password_hash, u.display_name, u.role,
                          u.linked_line_user_id, u.enabled, u.access_control_version,
                          EXISTS(SELECT 1 FROM admin_root_account r WHERE r.admin_user_id=u.id) AS is_root
                   FROM admin_users u WHERE username=%s FOR UPDATE""",
                (normalized_username,),
            )
            row = cursor.fetchone()
            if _is_rate_limited(cursor, normalized_username, source_identifier):
                _record_login_attempt(cursor, normalized_username, source_identifier, "rate_limited")
                conn.commit()
                raise AdminLoginRateLimitedError()
            if not row or not row["enabled"] or not verify_admin_password(password, row["password_hash"]):
                _record_login_attempt(cursor, normalized_username, source_identifier, "failed")
                if row is not None and not row["enabled"]:
                    _record_disabled_account_login_attempt(cursor, normalized_username)
                conn.commit()
                return None
            factor = _active_factor_for_user(cursor, int(row["id"]))
            if factor is None:
                enrollment = _issue_mfa_enrollment(cursor, row)
                _record_login_attempt(cursor, normalized_username, source_identifier, "succeeded")
                _record_admin_audit_with_cursor(cursor, principal=_principal_from_row(cursor, row), action="admin.mfa.enrollment_issued", result_status=403)
                conn.commit()
                return enrollment
            challenge_id = str(uuid.uuid4())
            challenge_token = secrets.token_urlsafe(32)
            expires_at = _utc_now_naive() + timedelta(minutes=5)
            cursor.execute(
                """INSERT INTO admin_password_login_challenges (
                       id,admin_user_id,credential_version,factor_id,challenge_hash,source_hash,expires_at
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (challenge_id, row["id"], row["access_control_version"], factor["id"],
                 _token_hash(challenge_token), _attempt_subject_hash(source_identifier), expires_at),
            )
            _record_login_attempt(cursor, normalized_username, source_identifier, "succeeded")
            _record_admin_audit_with_cursor(cursor, principal=_principal_from_row(cursor, row), action="admin.password_challenge_issued", result_status=202)
        conn.commit()
        return PasswordLoginChallenge(challenge_id, challenge_token, expires_at)
    except pymysql.MySQLError as error:
        conn.rollback()
        raise AdminSessionStorageError("管理員登入儲存服務暫時無法使用") from error
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete_password_login_challenge(
    *, challenge_id: str, challenge_token: str, factor_code: str, source_identifier: str = "unknown",
) -> tuple[str, datetime, AdminPrincipal] | None:
    """Consume the password challenge and issue a Session only after factor proof."""
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """SELECT c.id,c.admin_user_id,c.credential_version,c.factor_id,c.challenge_hash,c.source_hash,
                          c.expires_at,c.consumed_at,u.id AS user_id,u.username,u.display_name,u.role,u.linked_line_user_id,
                          u.enabled,u.access_control_version
                   FROM admin_password_login_challenges c JOIN admin_users u ON u.id=c.admin_user_id
                   WHERE c.id=%s FOR UPDATE""",
                (challenge_id,),
            )
            challenge = cursor.fetchone()
            if (challenge is None or challenge["consumed_at"] is not None or challenge["expires_at"] <= _utc_now_naive()
                    or not hmac.compare_digest(str(challenge["challenge_hash"]), _token_hash(challenge_token))
                    or not hmac.compare_digest(str(challenge["source_hash"]), _attempt_subject_hash(source_identifier))
                    or not challenge["enabled"] or int(challenge["credential_version"]) != int(challenge["access_control_version"])):
                conn.commit()
                return None
            cursor.execute(
                """SELECT id,seed_ciphertext,encryption_key_version,last_successful_step
                   FROM admin_totp_factors WHERE id=%s AND admin_user_id=%s AND factor_state='active' FOR UPDATE""",
                (challenge["factor_id"], challenge["admin_user_id"]),
            )
            factor = cursor.fetchone()
            if factor is None:
                conn.commit()
                return None
            try:
                method = _verify_and_consume_second_factor(cursor, factor, factor_code)
            except AdminMfaReplayError:
                _record_login_attempt(cursor, str(challenge["username"]), source_identifier, "mfa_replay")
                conn.commit()
                return None
            if method is None:
                _record_login_attempt(cursor, str(challenge["username"]), source_identifier, "failed")
                conn.commit()
                return None
            cursor.execute("UPDATE admin_password_login_challenges SET consumed_at=UTC_TIMESTAMP(6) WHERE id=%s", (challenge_id,))
            row = {"id": challenge["user_id"], "username": challenge["username"], "display_name": challenge["display_name"], "role": challenge["role"], "linked_line_user_id": challenge["linked_line_user_id"], "enabled": challenge["enabled"], "access_control_version": challenge["access_control_version"], "is_root": False}
            cursor.execute("SELECT EXISTS(SELECT 1 FROM admin_root_account WHERE admin_user_id=%s) AS is_root", (challenge["user_id"],))
            row["is_root"] = bool(cursor.fetchone()["is_root"])
            now = _utc_now_naive()
            absolute_expires_at = now + timedelta(minutes=ADMIN_SESSION_MAXIMUM_MINUTES)
            expires_at = _session_expiry(now, absolute_expires_at)
            token = secrets.token_urlsafe(48)
            cursor.execute("""INSERT INTO admin_sessions (admin_user_id,session_token_hash,expires_at,absolute_expires_at,last_seen_at)
                              VALUES (%s,%s,%s,%s,%s)""", (challenge["user_id"], _token_hash(token), expires_at, absolute_expires_at, now))
            cursor.execute("UPDATE admin_users SET last_login_at=%s WHERE id=%s", (now, challenge["user_id"]))
            principal = _principal_from_row(cursor, row)
            _record_admin_audit_with_cursor(cursor, principal=principal, action="admin.login.success", result_status=200, details={"mfa_method": method})
            _record_login_attempt(cursor, str(challenge["username"]), source_identifier, "succeeded")
        conn.commit()
        return token, expires_at, principal
    except pymysql.MySQLError as error:
        conn.rollback()
        raise AdminSessionStorageError("管理員登入儲存服務暫時無法使用") from error
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def authenticate_local_developer_root(
    username: str, password: str, *, source_identifier: str = "local_developer_session"
) -> tuple[str, datetime, AdminPrincipal] | None:
    """Issue a local-only root Session after DB password verification, without bypassing Session authorization."""
    normalized_username = username.strip().lower()
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            _require_admin_session_schema(cursor)
            cursor.execute(
                """
                SELECT u.id, u.username, u.password_hash, u.display_name, u.role,
                       u.linked_line_user_id, u.enabled, u.access_control_version,
                       EXISTS(SELECT 1 FROM admin_root_account r WHERE r.admin_user_id=u.id) AS is_root
                FROM admin_users u WHERE u.username=%s FOR UPDATE
                """,
                (normalized_username,),
            )
            row = cursor.fetchone()
            if not row or not row["enabled"] or not row["is_root"]:
                conn.commit()
                return None
            if not verify_admin_password(password, row["password_hash"]):
                conn.commit()
                return None
            now = _utc_now_naive()
            absolute_expires_at = now + timedelta(minutes=ADMIN_SESSION_MAXIMUM_MINUTES)
            expires_at = _session_expiry(now, absolute_expires_at)
            token = secrets.token_urlsafe(48)
            cursor.execute(
                """INSERT INTO admin_sessions (
                    admin_user_id, session_token_hash, expires_at, absolute_expires_at, last_seen_at
                ) VALUES (%s,%s,%s,%s,%s)""",
                (row["id"], _token_hash(token), expires_at, absolute_expires_at, now),
            )
            cursor.execute("UPDATE admin_users SET last_login_at=%s WHERE id=%s", (now, row["id"]))
            principal = _principal_from_row(cursor, row)
            _record_admin_audit_with_cursor(
                cursor, principal=principal, action="admin.development_session_issued", result_status=200,
                details={"source": source_identifier},
            )
        conn.commit()
        return token, expires_at, principal
    except AdminSessionSchemaError:
        conn.rollback()
        raise
    except pymysql.MySQLError as error:
        conn.rollback()
        raise AdminSessionStorageError("開發 root Session 儲存服務暫時無法使用") from error
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete_mfa_enrollment(
    *, challenge_id: str, challenge_token: str, totp_code: str
) -> tuple[str, ...]:
    """Activate a password-bound short-lived factor challenge without issuing a Session."""
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """SELECT id, admin_user_id, challenge_hash, expires_at, consumed_at
                FROM admin_mfa_enrollment_challenges WHERE id=%s FOR UPDATE""",
                (challenge_id,),
            )
            challenge = cursor.fetchone()
            if (
                challenge is None
                or challenge["consumed_at"] is not None
                or challenge["expires_at"] <= _utc_now_naive()
                or not hmac.compare_digest(str(challenge["challenge_hash"]), _token_hash(challenge_token))
            ):
                raise ValueError("mfa_challenge_expired")
            cursor.execute(
                """SELECT id, seed_ciphertext, encryption_key_version, last_successful_step
                FROM admin_totp_factors WHERE admin_user_id=%s
                  AND factor_state='enrollment_pending' FOR UPDATE""",
                (challenge["admin_user_id"],),
            )
            factor = cursor.fetchone()
            if factor is None:
                raise ValueError("mfa_challenge_expired")
            method = _verify_and_consume_second_factor(cursor, factor, totp_code)
            if method != "totp":
                raise ValueError("invalid_credentials_or_factor")
            codes = generate_recovery_codes()
            cursor.execute(
                """UPDATE admin_totp_factors SET factor_state='active', activated_at=UTC_TIMESTAMP(6),
                enrollment_challenge_hash='', enrollment_expires_at=UTC_TIMESTAMP(6) WHERE id=%s""",
                (factor["id"],),
            )
            cursor.execute(
                "UPDATE admin_mfa_enrollment_challenges SET consumed_at=UTC_TIMESTAMP(6) WHERE id=%s",
                (challenge_id,),
            )
            cursor.executemany(
                "INSERT INTO admin_totp_recovery_codes (factor_id, code_hash) VALUES (%s,%s)",
                [(factor["id"], hash_recovery_code(code)) for code in codes],
            )
            cursor.execute(
                "SELECT id, username, display_name, role, linked_line_user_id, enabled, access_control_version, "
                "EXISTS(SELECT 1 FROM admin_root_account r WHERE r.admin_user_id=u.id) AS is_root "
                "FROM admin_users u WHERE id=%s",
                (challenge["admin_user_id"],),
            )
            principal = _principal_from_row(cursor, cursor.fetchone())
            _record_admin_audit_with_cursor(
                cursor, principal=principal, action="admin.mfa.enrollment_completed", result_status=200,
            )
        conn.commit()
        return codes
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
                       u.linked_line_user_id, u.access_control_version,
                       EXISTS(SELECT 1 FROM admin_root_account r
                              WHERE r.admin_user_id=u.id) AS is_root
                FROM admin_sessions s
                JOIN admin_users u ON u.id=s.admin_user_id
                WHERE s.session_token_hash=%s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > UTC_TIMESTAMP()
                  AND s.absolute_expires_at > UTC_TIMESTAMP()
                  AND u.enabled=TRUE
                LIMIT 1
                """,
                (_token_hash(token),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            cursor.execute(
                """
                UPDATE admin_sessions
                SET expires_at=LEAST(
                        DATE_ADD(UTC_TIMESTAMP(), INTERVAL 30 MINUTE),
                        absolute_expires_at
                    ),
                    last_seen_at=UTC_TIMESTAMP()
                WHERE session_token_hash=%s
                  AND revoked_at IS NULL
                  AND absolute_expires_at > UTC_TIMESTAMP()
                """,
                (_token_hash(token),),
            )
            principal = _principal_from_row(cursor, row)
        conn.commit()
        return principal
    except pymysql.MySQLError as error:
        raise AdminSessionStorageError("管理員 Session 服務暫時無法使用") from error
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
    except pymysql.MySQLError as error:
        raise AdminSessionStorageError("管理員 Session 服務暫時無法使用") from error
    finally:
        conn.close()


def renew_admin_session(token: str, *, session_minutes: int) -> datetime | None:
    """Extend a valid session without exposing or replacing its stored hash."""
    if not token:
        return None
    del session_minutes
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE admin_sessions s
                JOIN admin_users u ON u.id=s.admin_user_id
                SET s.expires_at=LEAST(
                        DATE_ADD(UTC_TIMESTAMP(), INTERVAL 30 MINUTE),
                        s.absolute_expires_at
                    ),
                    s.last_seen_at=UTC_TIMESTAMP()
                WHERE s.session_token_hash=%s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > UTC_TIMESTAMP()
                  AND s.absolute_expires_at > UTC_TIMESTAMP()
                  AND u.enabled=TRUE
                """,
                (_token_hash(token),),
            )
            renewed = cursor.rowcount > 0
            if renewed:
                cursor.execute(
                    "SELECT expires_at FROM admin_sessions WHERE session_token_hash=%s",
                    (_token_hash(token),),
                )
                row = cursor.fetchone()
        conn.commit()
        return row[0] if renewed and row else None
    except pymysql.MySQLError as error:
        raise AdminSessionStorageError("管理員 Session 服務暫時無法使用") from error
    finally:
        conn.close()


def _require_admin_session_schema(cursor: Any) -> None:
    cursor.execute(
        "SELECT COLUMN_NAME AS column_name FROM information_schema.columns "
        "WHERE table_schema=DATABASE() AND table_name='admin_sessions'"
    )
    available = {str(row["column_name"]) for row in cursor.fetchall()}
    missing = sorted(REQUIRED_ADMIN_SESSION_COLUMNS - available)
    if missing:
        raise AdminSessionSchemaError(
            "管理員 Session schema 尚未完成：缺少 " + ", ".join(missing)
        )


def has_required_role(principal: AdminPrincipal, minimum_role: str) -> bool:
    return principal.role in ROLE_LEVELS and minimum_role in ROLE_LEVELS


def has_required_capability(principal: AdminPrincipal, capability: str) -> bool:
    if capability not in CAPABILITY_REGISTRY:
        return False
    return capability in principal.effective_capabilities()


def _principal_from_row(_cursor: Any, row: dict[str, Any]) -> AdminPrincipal:
    role = str(row["role"])
    return AdminPrincipal(
        id=int(row["id"]), username=row["username"], display_name=row["display_name"],
        role=role, linked_line_user_id=row.get("linked_line_user_id"),
        is_root=bool(row.get("is_root", False)), enabled=bool(row.get("enabled", True)),
        access_control_version=int(row.get("access_control_version", 1)),
    )


def _active_factor_for_user(cursor: Any, admin_user_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT id, seed_ciphertext, encryption_key_version, last_successful_step
        FROM admin_totp_factors
        WHERE admin_user_id=%s AND factor_state='active'
        FOR UPDATE
        """,
        (admin_user_id,),
    )
    return cursor.fetchone()


def _issue_mfa_enrollment(cursor: Any, user: dict[str, Any]) -> MfaEnrollmentChallenge:
    """Replace a pending factor only; an active factor is never silently rotated."""
    try:
        cipher = totp_cipher_from_environment()
        secret = generate_totp_secret()
        encrypted = cipher.encrypt(secret)
    except TotpError as error:
        raise AdminMfaConfigurationError("管理員 MFA 暫時無法使用") from error
    challenge_id = str(uuid.uuid4())
    challenge_token = secrets.token_urlsafe(32)
    expires_at = _utc_now_naive() + timedelta(minutes=10)
    challenge_hash = _token_hash(challenge_token)
    cursor.execute(
        """SELECT id FROM admin_totp_factors WHERE admin_user_id=%s FOR UPDATE""",
        (user["id"],),
    )
    pending = cursor.fetchone()
    if pending is None:
        cursor.execute(
            """INSERT INTO admin_totp_factors (
                admin_user_id, factor_state, seed_ciphertext, encryption_key_version,
                enrollment_challenge_hash, enrollment_expires_at
            ) VALUES (%s,'enrollment_pending',%s,%s,%s,%s)""",
            (user["id"], encrypted.ciphertext, encrypted.key_version, challenge_hash, expires_at),
        )
    else:
        cursor.execute(
            """UPDATE admin_totp_factors SET factor_state='enrollment_pending', seed_ciphertext=%s,
                encryption_key_version=%s, enrollment_challenge_hash=%s, enrollment_expires_at=%s,
                last_successful_step=NULL, activated_at=NULL, revoked_at=NULL WHERE id=%s""",
            (encrypted.ciphertext, encrypted.key_version, challenge_hash, expires_at, pending["id"]),
        )
    cursor.execute(
        """INSERT INTO admin_mfa_enrollment_challenges (
            id, admin_user_id, challenge_hash, expires_at
        ) VALUES (%s,%s,%s,%s)""",
        (challenge_id, user["id"], challenge_hash, expires_at),
    )
    return MfaEnrollmentChallenge(
        challenge_id=challenge_id,
        challenge_token=challenge_token,
        provisioning_uri=provisioning_uri(
            secret=secret, account_name=str(user["username"]), issuer="Labor Union Admin"
        ),
        expires_at=expires_at,
    )


def _verify_and_consume_second_factor(
    cursor: Any, factor: dict[str, Any], supplied_code: str
) -> str | None:
    code = supplied_code.strip()
    if len(code) == 6 and code.isascii() and code.isdigit():
        try:
            cipher = totp_cipher_from_environment()
            secret = cipher.decrypt(
                EncryptedTotpSecret(
                    ciphertext=str(factor["seed_ciphertext"]),
                    key_version=str(factor["encryption_key_version"]),
                )
            )
            verification = verify_totp(secret=secret, code=code, now=datetime.now(timezone.utc))
        except (TotpError, TotpSecretUnavailableError) as error:
            raise AdminMfaConfigurationError("管理員 MFA 暫時無法使用") from error
        if verification is None:
            return None
        if factor.get("last_successful_step") == verification.matched_step:
            raise AdminMfaReplayError()
        cursor.execute(
            "UPDATE admin_totp_factors SET last_successful_step=%s WHERE id=%s",
            (verification.matched_step, factor["id"]),
        )
        return "totp"

    cursor.execute(
        """
        SELECT id, code_hash FROM admin_totp_recovery_codes
        WHERE factor_id=%s AND consumed_at IS NULL FOR UPDATE
        """,
        (factor["id"],),
    )
    for recovery in cursor.fetchall():
        if verify_recovery_code(code, str(recovery["code_hash"])):
            cursor.execute(
                "UPDATE admin_totp_recovery_codes SET consumed_at=UTC_TIMESTAMP(6) WHERE id=%s",
                (recovery["id"],),
            )
            return "recovery_code"
    return None


def _is_rate_limited(
    cursor: Any, username: str, source_identifier: str, *, now: datetime | None = None
) -> bool:
    """Use the shared clock boundary so the policy can be deterministically verified."""
    window_start = (now or _utc_now_naive()) - timedelta(minutes=LOGIN_ATTEMPT_WINDOW_MINUTES)
    cursor.execute(
        """
        SELECT COUNT(*) AS attempt_count FROM admin_login_attempts
        WHERE username_hash=%s AND source_hash=%s
          AND outcome IN ('failed', 'rate_limited', 'mfa_replay')
          AND occurred_at >= %s
        """,
        (_attempt_subject_hash(username), _attempt_subject_hash(source_identifier), window_start),
    )
    row = cursor.fetchone()
    return int(row["attempt_count"] if isinstance(row, dict) else row[0]) >= LOGIN_ATTEMPT_MAXIMUM


def _record_login_attempt(
    cursor: Any, username: str, source_identifier: str, outcome: str, *, now: datetime | None = None
) -> None:
    cursor.execute(
        """INSERT INTO admin_login_attempts (username_hash, source_hash, outcome, occurred_at)
        VALUES (%s,%s,%s,%s)""",
        (_attempt_subject_hash(username), _attempt_subject_hash(source_identifier), outcome, now or _utc_now_naive()),
    )
    if outcome in {"rate_limited", "mfa_replay"}:
        _record_admin_audit_with_cursor(
            cursor,
            principal=None,
            action=f"admin.login.{outcome}",
            result_status=429 if outcome == "rate_limited" else 401,
            details={"subject_hash": _attempt_subject_hash(username)},
        )


def _record_disabled_account_login_attempt(cursor: Any, username: str) -> None:
    """Record the security fact without changing the generic public login response."""
    _record_admin_audit_with_cursor(
        cursor,
        principal=None,
        action="admin.login.disabled_account",
        result_status=401,
        details={"subject_hash": _attempt_subject_hash(username)},
    )


def _record_admin_audit_with_cursor(
    cursor: Any,
    *,
    principal: AdminPrincipal | None,
    action: str,
    result_status: int | None,
    details: dict[str, Any] | None = None,
) -> None:
    cursor.execute(
        """INSERT INTO admin_audit_logs (
            admin_user_id, action, result_status, details_json
        ) VALUES (%s,%s,%s,%s)""",
        (
            principal.id if principal and principal.id is not None else None,
            action,
            result_status,
            json.dumps(mask_audit_details(details), ensure_ascii=False) if details else None,
        ),
    )
    _append_security_alert_outbox(
        cursor,
        source_audit_id=int(cursor.lastrowid),
        action=action,
        principal=principal,
        result_status=result_status,
        details=details,
    )


def _append_security_alert_outbox(
    cursor: Any,
    *,
    source_audit_id: int,
    action: str,
    principal: AdminPrincipal | None,
    result_status: int | None,
    details: dict[str, Any] | None,
) -> None:
    """Persist only high-risk alert intents in the same transaction as their audit fact."""
    alert_code = SECURITY_ALERT_ACTION_CODES.get(action)
    if action == "admin.login.success" and details and details.get("mfa_method") == "recovery_code":
        alert_code = "access_recovery_code_used"
    if alert_code is None:
        return
    alert_identity = hashlib.sha256(f"audit:{source_audit_id}".encode("ascii")).hexdigest()
    payload = {
        "reason": action,
        "source_audit_id": source_audit_id,
        "result_status": result_status,
        "actor_id": principal.id if principal and principal.id is not None else None,
        "audit_details": mask_audit_details(details) if details else None,
    }
    cursor.execute(
        """INSERT INTO admin_security_alert_outbox (
            source_audit_id,alert_code,alert_identity,payload_snapshot
        ) VALUES (%s,%s,%s,%s)""",
        (source_audit_id, alert_code, alert_identity, json.dumps(payload, ensure_ascii=False)),
    )


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
                    json.dumps(mask_audit_details(details), ensure_ascii=False) if details else None,
                ),
            )
        conn.commit()
    finally:
        conn.close()

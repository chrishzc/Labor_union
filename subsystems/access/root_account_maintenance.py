"""Transaction owner for interactive, offline root account maintenance."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

import pymysql

from subsystems.access import authentication_session as auth
from subsystems.access.totp import (
    EncryptedTotpSecret,
    TotpSecretCipher,
    generate_recovery_codes,
    hash_recovery_code,
    verify_totp,
)


_AUTHORIZATION_LIFETIME = timedelta(minutes=5)
_SOURCE = "windows_root_account_maintenance"


class RootMaintenanceRejected(Exception):
    """Safe rejection reason suitable for the maintenance terminal."""


class RootMaintenanceConflict(RootMaintenanceRejected):
    """Root identity, security version, or factor changed after verification."""


class RootMaintenanceCommitUnknown(Exception):
    """The connection did not acknowledge the commit."""


@dataclass(repr=False)
class VerifiedRoot:
    account_id: int
    username: str
    version: int
    factor_id: int
    expires_at: datetime
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    used: bool = field(default=False, init=False)


@dataclass(frozen=True, repr=False)
class RenameRoot:
    username: str


@dataclass(frozen=True, repr=False)
class ChangeRootPassword:
    password: str


@dataclass(frozen=True, repr=False)
class ReplaceRootTotp:
    encrypted: EncryptedTotpSecret
    verified_step: int


RootChange = RenameRoot | ChangeRootPassword | ReplaceRootTotp


def _locked_root(cursor):
    cursor.execute(
        """SELECT u.id, u.username, u.password_hash, u.enabled, u.access_control_version
           FROM admin_root_account r JOIN admin_users u ON u.id=r.admin_user_id
           WHERE r.singleton_key=1 FOR UPDATE"""
    )
    return cursor.fetchone()


def verify_root(
    connect: auth.ConnectionFactory, cipher: TotpSecretCipher,
    username: str, password: str, code: str,
) -> VerifiedRoot:
    """Consume only a current root TOTP and issue a short-lived in-process grant."""
    conn = connect()
    uow = auth.AccessControlUnitOfWork(conn)
    now = datetime.now(timezone.utc)
    username = username.strip().lower()
    try:
        uow.__enter__()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            root = _locked_root(cursor)
            if not root or not root["enabled"]:
                raise RootMaintenanceRejected("找不到啟用中的 root 帳號。")
            rate_subject = str(root["username"])
            if auth._is_rate_limited(cursor, rate_subject, _SOURCE):
                raise RootMaintenanceRejected("嘗試次數已達上限，請稍後重試。")
            outcome = "failed"
            factor = None
            if username == rate_subject and auth.verify_admin_password(password, root["password_hash"]):
                factor = auth._active_factor_for_user(cursor, root["id"])
                if factor is None:
                    raise RootMaintenanceRejected("root 沒有啟用中的驗證器，請走離線復原。")
                secret = cipher.decrypt(EncryptedTotpSecret(
                    ciphertext=factor["seed_ciphertext"],
                    key_version=factor["encryption_key_version"],
                ))
                verification = verify_totp(secret=secret, code=code, now=now)
                if verification is not None:
                    previous_step = factor["last_successful_step"]
                    if previous_step is not None and previous_step >= verification.matched_step:
                        outcome = "mfa_replay"
                    else:
                        cursor.execute(
                            "UPDATE admin_totp_factors SET last_successful_step=%s WHERE id=%s",
                            (verification.matched_step, factor["id"]),
                        )
                        outcome = "succeeded"
            auth._record_login_attempt(cursor, rate_subject, _SOURCE, outcome)
        uow.commit()
    except BaseException:
        uow.rollback()
        raise
    finally:
        conn.close()
    if outcome != "succeeded":
        raise RootMaintenanceRejected("root 帳號、密碼或 TOTP 驗證失敗。")
    return VerifiedRoot(
        account_id=root["id"], username=rate_subject, version=root["access_control_version"],
        factor_id=factor["id"], expires_at=now + _AUTHORIZATION_LIFETIME,
    )


def prepare_new_totp(
    cipher: TotpSecretCipher, secret: str, code: str,
) -> ReplaceRootTotp:
    verification = verify_totp(secret=secret, code=code, now=datetime.now(timezone.utc))
    if verification is None:
        raise RootMaintenanceRejected("新驗證器的動態碼錯誤，原綁定仍有效。")
    return ReplaceRootTotp(cipher.encrypt(secret), verification.matched_step)


def normalize_new_username(username: str) -> str:
    normalized = username.strip().lower()
    if not 1 <= len(normalized) <= 100 or not normalized.isprintable():
        raise RootMaintenanceRejected("登入名稱須為 1 至 100 個可顯示字元。")
    return normalized


def _prepare_change(
    cursor, grant: VerifiedRoot, new: RootChange, current_password_hash: str,
) -> tuple[str, tuple[str, ...]]:
    if isinstance(new, RenameRoot):
        username = normalize_new_username(new.username)
        cursor.execute(
            "SELECT id FROM admin_users WHERE username=%s FOR UPDATE", (username,),
        )
        existing = cursor.fetchone()
        if existing and existing["id"] == grant.account_id:
            raise RootMaintenanceRejected("新登入名稱必須和目前的名稱不同。")
        if existing:
            raise RootMaintenanceRejected("新登入名稱已被使用。")
        cursor.execute(
            "UPDATE admin_users SET username=%s WHERE id=%s",
            (username, grant.account_id),
        )
        return "rename", ()

    if isinstance(new, ChangeRootPassword):
        if not 10 <= len(new.password) <= 256:
            raise RootMaintenanceRejected("新密碼須為 10 至 256 個字元。")
        if auth.verify_admin_password(new.password, current_password_hash):
            raise RootMaintenanceRejected("新密碼必須和目前的密碼不同。")
        cursor.execute(
            "UPDATE admin_users SET password_hash=%s WHERE id=%s",
            (auth.hash_admin_password(new.password), grant.account_id),
        )
        return "password_change", ()

    # The schema owns one factor row per account. Replacing its seed revokes the
    # previous authenticator. Consume prior recovery codes before issuing new ones.
    cursor.execute(
        """UPDATE admin_totp_factors SET seed_ciphertext=%s, encryption_key_version=%s,
               enrollment_challenge_hash='', enrollment_expires_at=UTC_TIMESTAMP(6),
               last_successful_step=%s, activated_at=UTC_TIMESTAMP(6), revoked_at=NULL
           WHERE id=%s""",
        (new.encrypted.ciphertext, new.encrypted.key_version, new.verified_step, grant.factor_id),
    )
    cursor.execute(
        """UPDATE admin_totp_recovery_codes SET consumed_at=UTC_TIMESTAMP(6)
           WHERE factor_id=%s AND consumed_at IS NULL""",
        (grant.factor_id,),
    )
    codes = generate_recovery_codes()
    cursor.executemany(
        "INSERT INTO admin_totp_recovery_codes (factor_id, code_hash) VALUES (%s,%s)",
        [(grant.factor_id, hash_recovery_code(code)) for code in codes],
    )
    return "totp_replacement", codes


def apply_root_change(
    connect: auth.ConnectionFactory, grant: VerifiedRoot, new: RootChange,
) -> tuple[str, ...]:
    if grant.used or datetime.now(timezone.utc) >= grant.expires_at:
        raise RootMaintenanceRejected("本次驗證已失效，請重新驗證 root。")
    grant.used = True
    conn = connect()
    uow = auth.AccessControlUnitOfWork(conn)
    try:
        uow.__enter__()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            root = _locked_root(cursor)
            if datetime.now(timezone.utc) >= grant.expires_at:
                raise RootMaintenanceRejected("本次驗證已失效，請重新驗證 root。")
            if (not root or not root["enabled"] or root["id"] != grant.account_id
                    or root["access_control_version"] != grant.version):
                raise RootMaintenanceConflict("root 帳號或安全版本已變更，請重新驗證 root。")
            factor = auth._active_factor_for_user(cursor, grant.account_id)
            if factor is None or factor["id"] != grant.factor_id:
                raise RootMaintenanceConflict("原驗證器已變更，請重新驗證 root。")
            action, codes = _prepare_change(cursor, grant, new, root["password_hash"])
            cursor.execute(
                "UPDATE admin_users SET access_control_version=access_control_version+1 WHERE id=%s",
                (grant.account_id,),
            )
            cursor.execute(
                """UPDATE admin_sessions SET revoked_at=UTC_TIMESTAMP(6)
                   WHERE admin_user_id=%s AND revoked_at IS NULL""",
                (grant.account_id,),
            )
            for table in ("admin_password_login_challenges", "admin_mfa_enrollment_challenges"):
                cursor.execute(
                    f"""UPDATE {table} SET consumed_at=UTC_TIMESTAMP(6)
                        WHERE admin_user_id=%s AND consumed_at IS NULL""",
                    (grant.account_id,),
                )
            actor = auth.AdminPrincipal(
                id=grant.account_id, username=grant.username, display_name="",
                role="system_admin", is_root=True,
            )
            auth._record_admin_audit_with_cursor(
                cursor, principal=actor, action="admin.root.offline_maintenance",
                result_status=200, details={
                    "account_id": grant.account_id,
                    "operation": action,
                    "operation_id": grant.operation_id,
                    "resulting_version": grant.version + 1,
                    "reason": "routine_root_maintenance",
                },
            )
        try:
            uow.commit()
        except pymysql.MySQLError:
            raise RootMaintenanceCommitUnknown() from None
        return codes
    except RootMaintenanceCommitUnknown:
        raise
    except pymysql.err.IntegrityError:
        uow.rollback()
        raise RootMaintenanceRejected("帳號或安全資料發生衝突，變更已取消。") from None
    except BaseException:
        uow.rollback()
        raise
    finally:
        conn.close()


def read_commit_outcome(
    connect: auth.ConnectionFactory, grant: VerifiedRoot,
) -> Literal["committed", "unchanged", "unknown"]:
    """Read only. A repeated attempt never applies the mutation automatically."""
    conn = connect()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """SELECT u.access_control_version, EXISTS (
                       SELECT 1 FROM admin_audit_logs l
                       WHERE l.admin_user_id=u.id AND l.action='admin.root.offline_maintenance'
                         AND l.result_status=200
                         AND JSON_UNQUOTE(JSON_EXTRACT(l.details_json, '$.operation_id'))=%s
                   ) AS committed
                   FROM admin_root_account r JOIN admin_users u ON u.id=r.admin_user_id
                   WHERE r.singleton_key=1 AND u.id=%s""",
                (grant.operation_id, grant.account_id),
            )
            row = cursor.fetchone()
        if row and row["committed"] and row["access_control_version"] >= grant.version + 1:
            return "committed"
        if row and row["access_control_version"] == grant.version:
            return "unchanged"
        return "unknown"
    finally:
        conn.close()

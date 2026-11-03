"""Offline reset of a sole, unused root whose initial TOTP binding never completed."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re

import pymysql

from subsystems.access.authentication_session import (
    AccessControlUnitOfWork, ConnectionFactory, _record_admin_audit_with_cursor,
)


class IncompleteRootResetError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class IncompleteRootPreview:
    database: str
    account_id: int
    version: int


def _connection(connection_factory: ConnectionFactory, database: str):
    if os.getenv("APP_ENV", "").strip().lower() not in {"development", "dev", "local", "test"}:
        raise IncompleteRootResetError("development_required")
    if database != "union_db" and not re.fullmatch(r"lu_test_[a-z0-9_]+", database):
        raise IncompleteRootResetError("local_database_required")
    conn = connection_factory()
    if str(getattr(conn, "host", "")).lower() not in {"localhost", "127.0.0.1", "::1"}:
        conn.close()
        raise IncompleteRootResetError("loopback_required")
    return conn


def _candidate(cursor, database: str, *, lock: bool) -> IncompleteRootPreview:
    cursor.execute("SELECT DATABASE() AS database_name")
    if cursor.fetchone()["database_name"] != database:
        raise IncompleteRootResetError("database_mismatch")
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT u.id,u.access_control_version,u.last_login_at,u.linked_line_user_id,u.enabled "
        "FROM admin_root_account r JOIN admin_users u ON u.id=r.admin_user_id "
        "WHERE r.singleton_key=1" + suffix
    )
    root = cursor.fetchone()
    if root is None:
        raise IncompleteRootResetError("root_missing")
    if (not root["enabled"] or int(root["access_control_version"]) != 1
            or root["last_login_at"] is not None or root["linked_line_user_id"] is not None):
        raise IncompleteRootResetError("root_already_used")
    cursor.execute("SELECT id FROM admin_users ORDER BY id LIMIT 2" + suffix)
    if [row["id"] for row in cursor.fetchall()] != [root["id"]]:
        raise IncompleteRootResetError("other_admins_exist")
    cursor.execute("SELECT id FROM admin_sessions WHERE admin_user_id=%s LIMIT 1" + suffix, (root["id"],))
    if cursor.fetchone() is not None:
        raise IncompleteRootResetError("root_already_used")
    cursor.execute(
        "SELECT id,factor_state,activated_at,last_successful_step FROM admin_totp_factors WHERE admin_user_id=%s" + suffix,
        (root["id"],),
    )
    factors = cursor.fetchall()
    if any(row["factor_state"] != "enrollment_pending" or row["activated_at"] is not None
           or row["last_successful_step"] is not None for row in factors):
        raise IncompleteRootResetError("root_already_enrolled")
    cursor.execute(
        "SELECT 1 FROM admin_totp_recovery_codes c JOIN admin_totp_factors f ON f.id=c.factor_id "
        "WHERE f.admin_user_id=%s LIMIT 1", (root["id"],),
    )
    if cursor.fetchone() is not None:
        raise IncompleteRootResetError("root_already_enrolled")
    # Prevent SET NULL/CASCADE from silently changing business data on account deletion.
    cursor.execute(
        "SELECT TABLE_SCHEMA AS schema_name,TABLE_NAME AS table_name,COLUMN_NAME AS column_name "
        "FROM information_schema.KEY_COLUMN_USAGE WHERE REFERENCED_TABLE_SCHEMA=DATABASE() "
        "AND REFERENCED_TABLE_NAME='admin_users'"
    )
    auth_tables = {"admin_root_account", "admin_sessions", "admin_totp_factors",
                   "admin_password_login_challenges", "admin_mfa_enrollment_challenges", "admin_audit_logs"}
    for reference in cursor.fetchall():
        if reference["schema_name"] != database:
            raise IncompleteRootResetError("external_reference")
        table, column = reference["table_name"], reference["column_name"]
        if table in auth_tables:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_]+", table) or not re.fullmatch(r"[A-Za-z0-9_]+", column):
            raise IncompleteRootResetError("external_reference")
        cursor.execute(f"SELECT 1 FROM `{table}` WHERE `{column}`=%s LIMIT 1" + suffix, (root["id"],))
        if cursor.fetchone() is not None:
            raise IncompleteRootResetError("root_has_business_references")
    return IncompleteRootPreview(database, int(root["id"]), int(root["access_control_version"]))


def preview_incomplete_root_reset(*, connection_factory: ConnectionFactory, target_database: str) -> IncompleteRootPreview:
    conn = _connection(connection_factory, target_database)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            conn.begin()
            return _candidate(cursor, target_database, lock=False)
    finally:
        conn.rollback()
        conn.close()


def reset_incomplete_root_setup(*, connection_factory: ConnectionFactory, target_database: str,
                                expected_account_id: int, expected_version: int) -> None:
    conn = _connection(connection_factory, target_database)
    uow = AccessControlUnitOfWork(conn)
    try:
        uow.__enter__()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            current = _candidate(cursor, target_database, lock=True)
            if current.account_id != expected_account_id or current.version != expected_version:
                raise IncompleteRootResetError("admin_version_conflict")
            for table in ("admin_password_login_challenges", "admin_mfa_enrollment_challenges", "admin_totp_factors"):
                cursor.execute(f"DELETE FROM `{table}` WHERE admin_user_id=%s", (current.account_id,))
            cursor.execute("DELETE FROM admin_root_account WHERE singleton_key=1 AND admin_user_id=%s", (current.account_id,))
            if cursor.rowcount != 1:
                raise IncompleteRootResetError("admin_version_conflict")
            cursor.execute("DELETE FROM admin_users WHERE id=%s", (current.account_id,))
            if cursor.rowcount != 1:
                raise IncompleteRootResetError("admin_version_conflict")
            _record_admin_audit_with_cursor(cursor, principal=None, action="admin.root.incomplete_setup_reset",
                result_status=200, details={"account_id": current.account_id, "previous_version": current.version})
        uow.commit()
    except pymysql.MySQLError as error:
        uow.rollback()
        if error.args and error.args[0] in (1205, 1213):
            raise IncompleteRootResetError("admin_version_conflict") from None
        raise
    except Exception:
        uow.rollback()
        raise
    finally:
        conn.close()

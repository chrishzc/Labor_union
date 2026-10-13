"""Preserve the existing local root authentication facts across a schema reset.

This maintenance adapter copies facts, never creates an MFA seed or a session.
The durable backup is encrypted with the existing application TOTP keyring.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

import pymysql
from cryptography.fernet import Fernet

from subsystems.access.totp import EncryptedTotpSecret, TotpSecretCipher


class RootPreservationError(RuntimeError):
    """A reset cannot safely preserve the existing root authentication."""


TABLES = (
    "line_users", "admin_users", "admin_root_account", "admin_totp_factors",
    "admin_totp_recovery_codes", "admin_mfa_enrollment_challenges",
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _keyring() -> tuple[dict[str, str], str]:
    try:
        keys = dict(item.strip().split(":", 1) for item in os.environ.get(
            "ACCESS_CONTROL_TOTP_KEYRING", ""
        ).split(",") if item.strip())
        version = os.environ.get("ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION", "").strip()
        TotpSecretCipher(keys, version)
        return keys, version
    except Exception:
        raise RootPreservationError("root backup requires a valid existing TOTP keyring") from None


def _identity(config: dict[str, object]) -> dict[str, object]:
    return {"host": config["host"], "port": int(config.get("port") or 3306),
            "database": config["database"]}


def _read(cursor: Any) -> dict[str, list[dict[str, Any]]]:
    cursor.execute("SELECT * FROM admin_root_account WHERE singleton_key=1")
    root = cursor.fetchone()
    if root is None:
        cursor.execute("SELECT COUNT(*) AS count FROM admin_users")
        if cursor.fetchone()["count"]:
            raise RootPreservationError("admin accounts exist without a root designation; reset refused")
        return {table: [] for table in TABLES}
    root_id = root["admin_user_id"]
    cursor.execute("SELECT * FROM admin_users WHERE id=%s", (root_id,))
    user = cursor.fetchone()
    if user is None:
        raise RootPreservationError("root designation has no account; reset refused")
    rows = {table: [] for table in TABLES}
    rows["admin_users"] = [user]
    rows["admin_root_account"] = [root]
    if user["linked_line_user_id"]:
        cursor.execute("SELECT * FROM line_users WHERE line_user_id=%s", (user["linked_line_user_id"],))
        rows["line_users"] = list(cursor.fetchall())
        if not rows["line_users"]:
            raise RootPreservationError("root LINE identity parent is missing; reset refused")
    cursor.execute("SELECT * FROM admin_totp_factors WHERE admin_user_id=%s ORDER BY id", (root_id,))
    rows["admin_totp_factors"] = list(cursor.fetchall())
    cursor.execute(
        "SELECT c.* FROM admin_totp_recovery_codes c JOIN admin_totp_factors f "
        "ON f.id=c.factor_id WHERE f.admin_user_id=%s ORDER BY c.id", (root_id,),
    )
    rows["admin_totp_recovery_codes"] = list(cursor.fetchall())
    cursor.execute("SELECT * FROM admin_mfa_enrollment_challenges WHERE admin_user_id=%s ORDER BY id", (root_id,))
    rows["admin_mfa_enrollment_challenges"] = list(cursor.fetchall())
    return rows


def capture_root_authentication(
    config: dict[str, object], *, connection_factory: Callable[..., Any] = pymysql.connect,
) -> dict[str, list[dict[str, Any]]]:
    """Read only the designated root and its necessary foreign-key parents."""
    connection = connection_factory(**{k: v for k, v in config.items() if k != "database"})
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s", (config["database"],))
            tables = {row["name"] for row in cursor.fetchall()}
            if not tables:
                return {table: [] for table in TABLES}
            if not set(TABLES).issubset(tables):
                for table in TABLES[1:]:
                    if table in tables:
                        cursor.execute("SELECT COUNT(*) AS count FROM `" + str(config["database"]).replace("`", "``") + "`.`" + table + "`")
                        if cursor.fetchone()["count"]:
                            raise RootPreservationError("root preservation tables are incomplete; reset refused before DROP")
                return {table: [] for table in TABLES}
            cursor.execute("SELECT COUNT(*) AS count FROM information_schema.PROCESSLIST WHERE DB=%s AND ID<>CONNECTION_ID()", (config["database"],))
            if cursor.fetchone()["count"]:
                raise RootPreservationError("stop API, UI and workers before resetting the database")
            cursor.execute("USE `" + str(config["database"]).replace("`", "``") + "`")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
            snapshot = _read(cursor)
        return json.loads(_json(snapshot))
    except RootPreservationError:
        raise
    except Exception:
        raise RootPreservationError("cannot read root authentication; reset refused before DROP") from None
    finally:
        connection.rollback()
        connection.close()


def save_root_authentication(
    snapshot: dict[str, list[dict[str, Any]]], config: dict[str, object], path: Path,
) -> dict[str, object]:
    """Durably encrypt and verify the root backup before any destructive DDL."""
    if not snapshot["admin_users"]:
        return {"status": "no_existing_root", "root_account_count": 0}
    keys, version = _keyring()
    cipher = TotpSecretCipher(keys, version)
    try:
        for factor in snapshot["admin_totp_factors"]:
            if factor["factor_state"] in ("active", "enrollment_pending"):
                cipher.decrypt(EncryptedTotpSecret(factor["seed_ciphertext"], factor["encryption_key_version"]))
        encrypted = Fernet(keys[version].encode("ascii")).encrypt(
            _json({"identity": _identity(config), "tables": snapshot}).encode("utf-8")
        ).decode("ascii")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(_json({"format": "local-root-auth-v1", "key_version": version, "ciphertext": encrypted}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if load_root_authentication(path, config) != snapshot:
            raise RootPreservationError("root backup verification failed before DROP")
    except RootPreservationError:
        raise
    except Exception:
        raise RootPreservationError("root backup or factor decryption failed; reset refused before DROP") from None
    return {"status": "encrypted_and_verified", "root_account_count": 1,
            "factor_count": len(snapshot["admin_totp_factors"]),
            "recovery_code_count": len(snapshot["admin_totp_recovery_codes"]),
            "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load_root_authentication(path: Path, config: dict[str, object]) -> dict[str, list[dict[str, Any]]]:
    """Read an encrypted recovery artifact without exposing any secret values."""
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope["format"] != "local-root-auth-v1":
            raise ValueError()
        keys, _ = _keyring()
        payload = json.loads(Fernet(keys[envelope["key_version"]].encode("ascii")).decrypt(envelope["ciphertext"].encode("ascii")))
        if payload["identity"] != _identity(config) or set(payload["tables"]) != set(TABLES):
            raise ValueError()
        return payload["tables"]
    except Exception:
        raise RootPreservationError("root backup cannot be decrypted or belongs to another target") from None


def restore_root_authentication(
    snapshot: dict[str, list[dict[str, Any]]], config: dict[str, object],
    *, connection_factory: Callable[..., Any] = pymysql.connect,
) -> dict[str, object]:
    """Restore the same facts atomically, then compare every preserved field."""
    if not snapshot["admin_users"]:
        return {"status": "no_existing_root", "root_account_count": 0}
    connection = connection_factory(**config)
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            for table in TABLES:
                for row in snapshot[table]:
                    columns = ",".join("`" + name.replace("`", "``") + "`" for name in row)
                    placeholders = ",".join(["%s"] * len(row))
                    cursor.execute(f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})", tuple(row.values()))
            if json.loads(_json(_read(cursor))) != snapshot:
                raise RootPreservationError("restored root authentication does not match its backup")
        connection.commit()
        return {"status": "preserved", "root_account_count": 1,
                "factor_count": len(snapshot["admin_totp_factors"]),
                "recovery_code_count": len(snapshot["admin_totp_recovery_codes"])}
    except Exception:
        connection.rollback()
        raise RootPreservationError("root authentication restore failed; use the retained encrypted backup") from None
    finally:
        connection.close()

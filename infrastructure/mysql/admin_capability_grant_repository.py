"""Durable capability-grant administration with one transaction per command."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Literal

from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.access.authentication_session import (
    CAPABILITY_REGISTRY,
    AdminPrincipal,
    has_required_capability,
)


GrantAction = Literal["grant", "revoke"]


class CapabilityGrantError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CapabilityGrantCommand:
    target_admin_user_id: int
    capability: str
    action: GrantAction
    expected_authorization_version: int
    reason: str
    idempotency_key: str
    correlation_id: str
    expires_at: datetime | None = None


def apply_capability_grant(
    command: CapabilityGrantCommand, actor: AdminPrincipal
) -> dict[str, Any]:
    _validate_command(command, actor)
    connection = get_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            result = _apply_command(cursor, command, actor)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def list_active_capability_grants(admin_user_id: int) -> list[dict[str, Any]]:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT capability, effective_from, expires_at, granted_by_admin_user_id, reason
                FROM admin_capability_grants
                WHERE admin_user_id=%s AND revoked_at IS NULL
                ORDER BY capability
                """,
                (admin_user_id,),
            )
            return list(cursor.fetchall())
    finally:
        connection.close()


def _validate_command(command: CapabilityGrantCommand, actor: AdminPrincipal) -> None:
    if actor.id is None:
        raise CapabilityGrantError("actor_identity_required")
    if not has_required_capability(actor, "system.administration"):
        raise CapabilityGrantError("insufficient_capability")
    if command.capability not in CAPABILITY_REGISTRY:
        raise CapabilityGrantError("unknown_capability")
    if command.expected_authorization_version < 0:
        raise CapabilityGrantError("admin_version_conflict")
    if not command.reason.strip() or not command.idempotency_key.strip() or not command.correlation_id.strip():
        raise CapabilityGrantError("grant_command_invalid")
    if command.action == "grant" and command.expires_at is None:
        raise CapabilityGrantError("grant_expiry_required")
    if command.action == "revoke" and command.expires_at is not None:
        raise CapabilityGrantError("grant_command_invalid")


def _apply_command(cursor: Any, command: CapabilityGrantCommand, actor: AdminPrincipal) -> dict[str, Any]:
    existing = _existing_receipt(cursor, command)
    if existing is not None:
        return existing
    target = _locked_target(cursor, command.target_admin_user_id)
    before_version = int(target["authorization_version"])
    if before_version != command.expected_authorization_version:
        raise CapabilityGrantError("admin_version_conflict")
    if command.action == "revoke":
        _protect_last_system_admin(cursor, target, command.capability)
    _write_grant(cursor, command, int(actor.id))
    after_version = before_version + 1
    _write_event_and_revoke_sessions(cursor, command, target, int(actor.id), before_version, after_version)
    receipt = _receipt(command, before_version, after_version)
    cursor.execute(
        "INSERT INTO access_control_apply_receipts (idempotency_key,command_fingerprint,receipt_json) VALUES (%s,%s,%s)",
        (command.idempotency_key, _fingerprint(command), json.dumps(receipt, ensure_ascii=False)),
    )
    return receipt


def _existing_receipt(cursor: Any, command: CapabilityGrantCommand) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT command_fingerprint,receipt_json FROM access_control_apply_receipts WHERE idempotency_key=%s FOR UPDATE",
        (command.idempotency_key,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if row["command_fingerprint"] != _fingerprint(command):
        raise CapabilityGrantError("idempotency_conflict")
    return json.loads(row["receipt_json"])


def _locked_target(cursor: Any, admin_user_id: int) -> dict[str, Any]:
    cursor.execute(
        "SELECT id,role,enabled,authorization_version FROM admin_users WHERE id=%s FOR UPDATE",
        (admin_user_id,),
    )
    target = cursor.fetchone()
    if target is None or not target["enabled"]:
        raise CapabilityGrantError("admin_user_not_active")
    return target


def _protect_last_system_admin(cursor: Any, target: dict[str, Any], capability: str) -> None:
    if capability != "system.administration" or target["role"] == "system_admin":
        return
    cursor.execute(
        """
        SELECT user.id FROM admin_users user
        WHERE user.enabled=TRUE AND (
          user.role='system_admin' OR EXISTS (
            SELECT 1 FROM admin_capability_grants grant_row
            WHERE grant_row.admin_user_id=user.id
              AND grant_row.capability='system.administration'
              AND grant_row.revoked_at IS NULL
              AND grant_row.effective_from <= UTC_TIMESTAMP()
              AND (grant_row.expires_at IS NULL OR grant_row.expires_at > UTC_TIMESTAMP())
          )
        )
        FOR UPDATE
        """
    )
    if len(cursor.fetchall()) <= 1:
        raise CapabilityGrantError("last_system_admin_protected")


def _write_grant(cursor: Any, command: CapabilityGrantCommand, actor_id: int) -> None:
    if command.action == "grant":
        cursor.execute(
            """
            INSERT INTO admin_capability_grants
              (admin_user_id,capability,granted_by_admin_user_id,reason,effective_from,expires_at)
            VALUES (%s,%s,%s,%s,UTC_TIMESTAMP(),%s)
            ON DUPLICATE KEY UPDATE granted_by_admin_user_id=VALUES(granted_by_admin_user_id),
              reason=VALUES(reason),effective_from=VALUES(effective_from),expires_at=VALUES(expires_at),
              revoked_at=NULL,revoked_by_admin_user_id=NULL,revoked_reason=NULL
            """,
            (command.target_admin_user_id, command.capability, actor_id, command.reason.strip(), command.expires_at),
        )
        return
    cursor.execute(
        """
        UPDATE admin_capability_grants
        SET revoked_at=UTC_TIMESTAMP(),revoked_by_admin_user_id=%s,revoked_reason=%s
        WHERE admin_user_id=%s AND capability=%s AND revoked_at IS NULL
        """,
        (actor_id, command.reason.strip(), command.target_admin_user_id, command.capability),
    )
    if cursor.rowcount != 1:
        raise CapabilityGrantError("capability_grant_not_active")


def _write_event_and_revoke_sessions(cursor: Any, command: CapabilityGrantCommand, target: dict[str, Any], actor_id: int, before_version: int, after_version: int) -> None:
    cursor.execute("UPDATE admin_users SET authorization_version=%s WHERE id=%s", (after_version, target["id"]))
    cursor.execute("UPDATE admin_sessions SET revoked_at=COALESCE(revoked_at,UTC_TIMESTAMP()) WHERE admin_user_id=%s", (target["id"],))
    cursor.execute(
        """
        INSERT INTO access_control_events
          (admin_user_id,actor_admin_user_id,event_type,capability,before_authorization_version,after_authorization_version,reason,idempotency_key,correlation_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (target["id"], actor_id, _event_type(command.action), command.capability, before_version, after_version, command.reason.strip(), command.idempotency_key, command.correlation_id),
    )


def _receipt(command: CapabilityGrantCommand, before_version: int, after_version: int) -> dict[str, Any]:
    return {"target_admin_user_id": command.target_admin_user_id, "capability": command.capability, "action": command.action, "before_authorization_version": before_version, "authorization_version": after_version}


def _event_type(action: GrantAction) -> str:
    return "capability_granted" if action == "grant" else "capability_revoked"


def _fingerprint(command: CapabilityGrantCommand) -> str:
    payload = {"target": command.target_admin_user_id, "capability": command.capability, "action": command.action, "expected": command.expected_authorization_version, "reason": command.reason.strip(), "expires_at": command.expires_at.isoformat() if command.expires_at else None, "correlation_id": command.correlation_id}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

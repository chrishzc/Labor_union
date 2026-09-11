"""MySQL adapter for Staff Bank Account current facts and safe audit events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from domains.staff.bank_account import StaffBankAccountCommand, account_last4
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.staff.bank_account_workflow import StaffBankAccountSnapshot


_FAMILY = "staff_bank_account_change/v1"


class MySqlStaffBankAccountRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load(self, staff_id: int, *, for_update: bool) -> Mapping[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM staff WHERE id=%s" + suffix, (staff_id,))
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                "SELECT aggregate_version FROM staff_bank_account_states WHERE staff_id=%s" + suffix,
                (staff_id,),
            )
            state = cursor.fetchone()
            cursor.execute(
                "SELECT id,bank_code,branch_code,account_no,is_primary,is_active "
                "FROM staff_bank_accounts WHERE staff_id=%s ORDER BY is_primary DESC,is_active DESC,id ASC"
                + suffix,
                (staff_id,),
            )
            accounts = tuple(cursor.fetchall() or ())
        return {
            "staff_id": staff_id,
            "aggregate_version": int((state or {}).get("aggregate_version") or 0),
            "accounts": accounts,
        }

    def account_owner(self, account_no: str, *, for_update: bool) -> int | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM staff_bank_accounts WHERE account_no=%s LIMIT 1" + suffix,
                (account_no,),
            )
            row = cursor.fetchone()
        return int(row["id"]) if row is not None else None

    def claim(self, *, staff_id: int, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, correlation_id: CorrelationId) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO application_command_claims "
                "(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (key.value, _FAMILY, str(staff_id), command_fingerprint.value, correlation_id.value),
            )
            if cursor.rowcount == 1:
                return
            cursor.execute(
                "SELECT command_family,aggregate_identity,command_fingerprint "
                "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
                (key.value,),
            )
            claim = cursor.fetchone()
        if (
            claim is None
            or claim["command_family"] != _FAMILY
            or claim["aggregate_identity"] != str(staff_id)
            or claim["command_fingerprint"] != command_fingerprint.value
        ):
            raise ValueError("idempotency_mismatch")

    def load_receipt(self, key: IdempotencyKey, *, for_update: bool) -> Mapping[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s" + suffix,
                (_FAMILY, key.value),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {"request_fingerprint": row["request_fingerprint"], "result": _decode(row["result_snapshot"])}

    def persist(self, *, snapshot: StaffBankAccountSnapshot, command: StaffBankAccountCommand, candidate: StaffBankAccountSnapshot, actor: ActorContext, reason: str, key: IdempotencyKey, correlation_id: CorrelationId) -> tuple[int, int]:
        before = next(
            (item for item in snapshot.accounts if item.account_id == command.account_id),
            None,
        )
        with self._connection.cursor() as cursor:
            if command.operation == "add":
                if candidate.accounts[-1].is_primary:
                    cursor.execute(
                        "UPDATE staff_bank_accounts SET is_primary=0 WHERE staff_id=%s",
                        (snapshot.staff_id,),
                    )
                cursor.execute(
                    "INSERT INTO staff_bank_accounts "
                    "(staff_id,bank_code,branch_code,account_no,is_primary,is_active) "
                    "VALUES (%s,%s,%s,%s,%s,1)",
                    (
                        snapshot.staff_id,
                        command.bank_code,
                        command.branch_code,
                        command.account_no,
                        candidate.accounts[-1].is_primary,
                    ),
                )
                account_id = int(cursor.lastrowid)
            elif command.operation == "replace":
                assert command.account_id is not None
                target = next(item for item in candidate.accounts if item.account_id == command.account_id)
                if target.is_primary:
                    cursor.execute(
                        "UPDATE staff_bank_accounts SET is_primary=0 WHERE staff_id=%s",
                        (snapshot.staff_id,),
                    )
                cursor.execute(
                    "UPDATE staff_bank_accounts SET bank_code=%s,branch_code=%s,account_no=%s,"
                    "is_primary=%s,is_active=1 WHERE id=%s AND staff_id=%s",
                    (
                        command.bank_code,
                        command.branch_code,
                        command.account_no,
                        target.is_primary,
                        command.account_id,
                        snapshot.staff_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError("staff_bank_account_not_found")
                account_id = command.account_id
            elif command.operation == "set_primary":
                assert command.account_id is not None
                cursor.execute(
                    "UPDATE staff_bank_accounts SET is_primary=0 WHERE staff_id=%s",
                    (snapshot.staff_id,),
                )
                cursor.execute(
                    "UPDATE staff_bank_accounts SET is_primary=1 WHERE id=%s AND staff_id=%s AND is_active=1",
                    (command.account_id, snapshot.staff_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("staff_bank_account_not_found")
                account_id = command.account_id
            else:
                assert command.account_id is not None
                cursor.execute(
                    "UPDATE staff_bank_accounts SET is_primary=0,is_active=0 "
                    "WHERE id=%s AND staff_id=%s AND is_active=1",
                    (command.account_id, snapshot.staff_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("staff_bank_account_not_found")
                if command.successor_account_id is not None:
                    cursor.execute(
                        "UPDATE staff_bank_accounts SET is_primary=1 "
                        "WHERE id=%s AND staff_id=%s AND is_active=1",
                        (command.successor_account_id, snapshot.staff_id),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("staff_bank_successor_invalid")
                account_id = command.account_id

            resulting_version = snapshot.version + 1
            cursor.execute(
                "INSERT INTO staff_bank_account_states (staff_id,aggregate_version,updated_by) "
                "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "aggregate_version=VALUES(aggregate_version),updated_by=VALUES(updated_by)",
                (snapshot.staff_id, resulting_version, actor.actor_id),
            )
            after = next(
                (
                    item for item in candidate.accounts
                    if item.account_id == account_id
                    or (command.operation == "add" and item.account_id == 0)
                ),
                None,
            )
            cursor.execute(
                "INSERT INTO staff_bank_account_events "
                "(staff_id,account_id,operation,expected_version,resulting_version,bank_code,branch_code,"
                "account_last4,was_primary,is_primary,was_active,is_active,actor_id,reason,idempotency_key,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    snapshot.staff_id,
                    account_id,
                    command.operation,
                    snapshot.version,
                    resulting_version,
                    after.bank_code if after is not None else None,
                    after.branch_code if after is not None else None,
                    account_last4(after.account_no) if after is not None else None,
                    before.is_primary if before is not None else False,
                    after.is_primary if after is not None else False,
                    before.is_active if before is not None else False,
                    after.is_active if after is not None else True,
                    actor.actor_id,
                    reason,
                    key.value,
                    correlation_id.value,
                ),
            )
        return account_id, resulting_version

    def save_receipt(self, *, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, preview_fingerprint: PreviewFingerprint, actor: ActorContext, reason: str, result: Mapping[str, Any]) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (_FAMILY, key.value, command_fingerprint.value, preview_fingerprint.value,
                 actor.actor_id, reason, _json(result)),
            )


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("staff_bank_receipt_invalid")
    return decoded


__all__ = ["MySqlStaffBankAccountRepository"]

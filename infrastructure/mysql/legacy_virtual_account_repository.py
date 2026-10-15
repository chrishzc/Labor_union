"""MySQL adapter for legacy per-order virtual-account mappings."""

from __future__ import annotations

import json

from subsystems.client_finance.case_virtual_account import AccountMapping


class MySqlLegacyVirtualAccountRepository:
    _COMMAND_FAMILY = "client_finance_legacy_virtual_account_workbook"
    _CASE_COMMAND_FAMILY = "client_finance_case_virtual_account"

    def __init__(self, connection) -> None:
        self.connection = connection

    def acquire_lock(self, key: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s,5) AS acquired", (self._lock_name(key),))
            row = cursor.fetchone()
        return bool(row and row["acquired"] == 1)

    def release_lock(self, key: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (self._lock_name(key),))

    def row_state(self, case_no: str, virtual_account: str, *, lock: bool) -> str:
        suffix = " FOR UPDATE" if lock else ""
        with self.connection.cursor() as cursor:
            cursor.execute(f"SELECT case_no FROM orders WHERE case_no=%s{suffix}", (case_no,))
            if cursor.fetchone() is None:
                return "missing_order"
            cursor.execute(
                f"SELECT id FROM client_legacy_virtual_accounts WHERE case_no=%s AND virtual_account=%s{suffix}",
                (case_no, virtual_account),
            )
            return "existing" if cursor.fetchone() is not None else "create"

    def insert_mapping(self, case_no: str, virtual_account: str, source_digest: str, source_row: int, actor: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO client_legacy_virtual_accounts "
                "(case_no,virtual_account,source_content_digest,source_row,created_by) VALUES (%s,%s,%s,%s,%s)",
                (case_no, virtual_account, source_digest, source_row, actor),
            )
            return cursor.rowcount == 1

    def load_receipt(self, key: str):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,preview_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s FOR UPDATE",
                (self._COMMAND_FAMILY, key),
            )
            return cursor.fetchone()

    def save_receipt(self, key: str, request_fingerprint: str, preview_fingerprint: str, actor: str, result: dict[str, object]) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    self._COMMAND_FAMILY,
                    key,
                    request_fingerprint,
                    preview_fingerprint,
                    actor,
                    "Legacy virtual-account workbook import",
                    json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ),
            )

    @staticmethod
    def _lock_name(key: str) -> str:
        del key
        return "client-finance:legacy-va-import"

    def load_case_mappings(self, case_no: str, *, lock: bool) -> tuple[AccountMapping, ...] | None:
        suffix = " FOR UPDATE" if lock else ""
        with self.connection.cursor() as cursor:
            cursor.execute(f"SELECT case_no FROM orders WHERE case_no=%s{suffix}", (case_no,))
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                "SELECT id,virtual_account FROM client_legacy_virtual_accounts "
                f"WHERE case_no=%s ORDER BY virtual_account,id{suffix}", (case_no,),
            )
            return tuple(AccountMapping(int(row["id"]), str(row["virtual_account"])) for row in cursor.fetchall())

    def account_used_by_other_case(self, case_no: str, account: str, *, lock: bool) -> bool:
        suffix = " FOR UPDATE" if lock else ""
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no FROM client_legacy_virtual_accounts "
                f"WHERE virtual_account=%s AND case_no<>%s ORDER BY case_no{suffix}", (account, case_no),
            )
            return cursor.fetchone() is not None

    def load_case_account_receipt(self, key: str):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,actor,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s FOR UPDATE", (self._CASE_COMMAND_FAMILY, key),
            )
            return cursor.fetchone()

    def replace_case_account(self, case_no: str, account: str, digest: str, actor: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("DELETE FROM client_legacy_virtual_accounts WHERE case_no=%s", (case_no,))
            cursor.execute(
                "INSERT INTO client_legacy_virtual_accounts "
                "(case_no,virtual_account,source_content_digest,source_row,created_by) VALUES (%s,%s,%s,2,%s)",
                (case_no, account, digest, actor),
            )

    def save_case_account_receipt(self, key: str, command: str, actor: str, result: dict) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                # Legacy required column; this direct command has no human preview.
                (self._CASE_COMMAND_FAMILY, key, command, command, actor, "後台客戶名冊虛擬帳號更新", json.dumps(result, ensure_ascii=False, sort_keys=True)),
            )


__all__ = ["MySqlLegacyVirtualAccountRepository"]

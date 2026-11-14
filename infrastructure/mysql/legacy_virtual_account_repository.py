"""MySQL adapter for legacy per-order virtual-account mappings."""

from __future__ import annotations

import json

from domains.client_finance.virtual_account import allows_historical_non_citizen_account
from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.nas_mutations import call_mutation
from subsystems.client_finance.case_virtual_account import AccountMapping, AccountOccupant
from subsystems.client_finance.virtual_account_resolution import (
    resolve_case_virtual_account,
    resolve_formula_case_virtual_account,
    resolve_imported_virtual_account,
)


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

    def effective_non_citizen_account_owner(self, account: str) -> str | None:
        with self.connection.cursor() as cursor:
            imported = resolve_imported_virtual_account(cursor, account)
        case_no = imported["case_no"] if imported is not None else None
        return case_no if case_no and allows_historical_non_citizen_account(case_no) else None

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

    def resolve_formula_account(self, case_no: str) -> str | None:
        with self.connection.cursor() as cursor:
            return resolve_formula_case_virtual_account(cursor, case_no)

    def resolve_effective_account(self, case_no: str) -> str | None:
        with self.connection.cursor() as cursor:
            return resolve_case_virtual_account(cursor, case_no)["virtual_account"]

    def account_occupants(self, case_no: str, account: str, *, lock: bool) -> tuple[AccountOccupant, ...]:
        suffix = " FOR UPDATE" if lock else ""
        with self.connection.cursor() as cursor:
            if allows_historical_non_citizen_account(case_no):
                cursor.execute(
                    "SELECT m.id,m.case_no,(o.status=%s AND c.state='active') AS cancelled,"
                    "c.current_event_id AS cancellation_event_id "
                    "FROM client_legacy_virtual_accounts m JOIN orders o ON o.case_no=m.case_no "
                    "LEFT JOIN order_lifecycle_control_state c ON c.case_no=m.case_no "
                    "AND c.control_type='cancellation' AND c.control_key='order_cancelled' "
                    "WHERE m.virtual_account=%s AND m.case_no<>%s ORDER BY m.case_no,m.id" + suffix,
                    (OrderLifecycleStatus.CANCELLED.value, account, case_no),
                )
            else:
                cursor.execute(
                    "SELECT id,case_no,0 AS cancelled FROM client_legacy_virtual_accounts "
                    "WHERE virtual_account=%s AND case_no<>%s ORDER BY case_no,id" + suffix,
                    (account, case_no),
                )
            return tuple(
                AccountOccupant(int(row["id"]), str(row["case_no"]), bool(row["cancelled"]), row.get("cancellation_event_id"))
                for row in cursor.fetchall()
            )

    def load_case_account_receipt(self, key: str):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,actor,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s FOR UPDATE", (self._CASE_COMMAND_FAMILY, key),
            )
            return cursor.fetchone()

    def replace_case_account(self, case_no: str, account: str, digest: str, actor: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id FROM client_legacy_virtual_accounts WHERE case_no=%s ORDER BY id FOR UPDATE", (case_no,))
            expected = json.dumps([int(row["id"]) for row in cursor.fetchall()])
            call_mutation(cursor, "lu_nas_replace_case_account_v1", case_no, expected, account, digest, actor)

    def replace_historical_non_citizen_account(
        self, case_no: str, account: str, digest: str, actor: str, source_row: int,
        mapping_ids: tuple[int, ...], occupants: tuple[AccountOccupant, ...],
    ) -> None:
        with self.connection.cursor() as cursor:
            call_mutation(
                cursor, "lu_nas_replace_case_account_v2", case_no, json.dumps(mapping_ids),
                account, digest, actor, source_row, json.dumps([item.id for item in occupants]),
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

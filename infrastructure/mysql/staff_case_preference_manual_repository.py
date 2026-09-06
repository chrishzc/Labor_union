"""MySQL adapter for the Staff six-relation manual owner."""

from __future__ import annotations

import json
from typing import Any

from domains.staff.case_preference_manual import (
    READ_ONLY_RELATION_SPECS, RELATION_KEYS, RELATION_SPECS, RelationValue, Relations,
    normalize_relations,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey


class MySqlStaffCasePreferenceManualRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def staff_exists(self, staff_id: int) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM staff WHERE id=%s LIMIT 1", (staff_id,))
            return cursor.fetchone() is not None

    def lock_staff(self, staff_id: int) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM staff WHERE id=%s FOR UPDATE", (staff_id,))
            if cursor.fetchone() is None:
                raise ValueError("staff_not_found")

    def load_relations(self, staff_id: int, *, for_update: bool) -> Relations:
        result: dict[str, list[dict[str, object]]] = {}
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            for key in sorted(RELATION_KEYS, key=lambda item: RELATION_SPECS[item][0]):
                table, value_column, detail_column = RELATION_SPECS[key]
                cursor.execute(
                    f"SELECT {value_column},{detail_column} FROM {table} WHERE staff_id=%s{suffix}",
                    (staff_id,),
                )
                result[key] = [
                    {"value": row.get(value_column), "detail": row.get(detail_column)}
                    for row in (cursor.fetchall() or ())
                ]
        return normalize_relations(result)

    def load_transportation(self, staff_id: int, *, for_update: bool = False) -> tuple[RelationValue, ...]:
        table, value_column, _detail_column = READ_ONLY_RELATION_SPECS["transportation"]
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {value_column} FROM {table} WHERE staff_id=%s{suffix}",
                (staff_id,),
            )
            return tuple(RelationValue(str(row[value_column]).strip()) for row in (cursor.fetchall() or ()))

    def replace_relations(self, staff_id: int, relations: Relations) -> None:
        with self._connection.cursor() as cursor:
            for key in sorted(RELATION_KEYS, key=lambda item: RELATION_SPECS[item][0]):
                table, value_column, detail_column = RELATION_SPECS[key]
                cursor.execute(f"DELETE FROM {table} WHERE staff_id=%s", (staff_id,))
                if relations[key]:
                    cursor.executemany(
                        f"INSERT INTO {table} (staff_id,{value_column},{detail_column}) VALUES (%s,%s,%s)",
                        [(staff_id, item.value, item.detail) for item in relations[key]],
                    )

    def find_receipt(self, key: IdempotencyKey, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s" + suffix,
                ("staff_case_preference_manual/v1", key.value),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        result = row["result_snapshot"]
        if isinstance(result, str):
            result = json.loads(result)
        return {"request_fingerprint": str(row["request_fingerprint"]), "result": result}

    def save_receipt(self, *, key: IdempotencyKey, request_fingerprint: PreviewFingerprint,
                     preview_fingerprint: PreviewFingerprint, actor: str, reason: str,
                     result: dict) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    "staff_case_preference_manual/v1", key.value, request_fingerprint.value,
                    preview_fingerprint.value, actor, reason,
                    json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ),
            )


__all__ = ["MySqlStaffCasePreferenceManualRepository"]


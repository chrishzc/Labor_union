"""
File: staff_historical_adoption_repository.py
Description: 鎖定 Staff、套用已裁決的歷史來源 scalar refresh並保存不可變 adoption receipt。
"""

from __future__ import annotations

from contextlib import contextmanager
import json


RELATION_COLUMNS = {
    "staff_regions": ("region_name", "custom_region_detail"),
    "staff_time_slots": ("slot_name", "custom_slot_detail"),
    "staff_cooking_skills": ("skill_name", "custom_skill_detail"),
    "staff_transportation": ("vehicle_type", None),
    "staff_holiday_availability": ("holiday_name", "custom_holiday_detail"),
    "staff_weekly_rest": ("rest_type", "custom_rest_detail"),
    "staff_baby_types": ("baby_type", "custom_baby_detail"),
    "staff_certifications": ("certification_type", None),
}


class MySqlStaffHistoricalAdoptionRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load_staff(self, identity_card: str, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute("SELECT * FROM staff WHERE identity_card=%s" + suffix, (identity_card,))
            rows = cursor.fetchall()
        return rows

    def create_staff(self, record: dict[str, object]) -> int:
        columns = tuple(sorted(record))
        assignments = ",".join(f"`{column}`" for column in columns)
        placeholders = ",".join("%s" for _ in columns)
        with _cursor(self._connection) as cursor:
            cursor.execute(
                f"INSERT INTO staff ({assignments}) VALUES ({placeholders})",
                tuple(record[column] for column in columns),
            )
            return int(cursor.lastrowid)

    def apply_scalar_patch(self, staff_id: int, patch: dict[str, object]) -> None:
        if not patch:
            return
        columns = tuple(sorted(patch))
        assignments = ",".join(f"`{column}`=%s" for column in columns)
        with _cursor(self._connection) as cursor:
            cursor.execute(
                f"UPDATE staff SET {assignments} WHERE id=%s",
                tuple(patch[column] for column in columns) + (staff_id,),
            )
            if int(cursor.rowcount) != 1:
                raise RuntimeError("staff_historical_adoption_stale")

    # 同一鎖定區段內完成快照比對、collision gate 與 replacement，避免集合半套寫入。
    def merge_bank_accounts(
        self,
        staff_id: int,
        incoming: tuple[tuple[object, ...], ...],
        *,
        replace_existing: bool = False,
    ):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT bank_code,branch_code,account_no,is_primary FROM staff_bank_accounts "
                "WHERE staff_id=%s FOR UPDATE",
                (staff_id,),
            )
            existing = {_bank_tuple(row) for row in cursor.fetchall()}
            candidate = {tuple(value) for value in incoming}
            if candidate == existing:
                return False, False
            if not replace_existing and not candidate:
                return False, False
            if not replace_existing and existing:
                return False, True
            if candidate and _has_cross_staff_bank_collision(cursor, staff_id, candidate):
                return False, True
            if replace_existing:
                cursor.execute(
                    "DELETE FROM staff_bank_accounts WHERE staff_id=%s",
                    (staff_id,),
                )
            if candidate:
                cursor.executemany(
                    "INSERT INTO staff_bank_accounts "
                    "(staff_id,bank_code,branch_code,account_no,is_primary) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    [(staff_id, *value) for value in sorted(candidate, key=str)],
                )
        return True, False

    # 關聯集合必須在同一 outer UoW 鎖定後整組替換，不能暴露中間狀態。
    def merge_relation(
        self,
        staff_id: int,
        table_name: str,
        incoming,
        *,
        replace_existing: bool = False,
    ):
        value_column, detail_column = RELATION_COLUMNS[table_name]
        selected_columns = value_column + (f",{detail_column}" if detail_column else "")
        with _cursor(self._connection) as cursor:
            cursor.execute(
                f"SELECT {selected_columns} FROM {table_name} WHERE staff_id=%s FOR UPDATE",
                (staff_id,),
            )
            existing = {_relation_tuple(row, value_column, detail_column) for row in cursor.fetchall()}
            candidate = {tuple(value) for value in incoming}
            if candidate == existing:
                return False, False
            if not replace_existing and not candidate:
                return False, False
            if not replace_existing and existing:
                return False, True
            if replace_existing:
                cursor.execute(
                    f"DELETE FROM {table_name} WHERE staff_id=%s",
                    (staff_id,),
                )
            columns = f"staff_id,{value_column}" + (f",{detail_column}" if detail_column else "")
            placeholders = ",".join(["%s"] * (2 + int(detail_column is not None)))
            if candidate:
                cursor.executemany(
                    f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})",
                    [(staff_id, *value) for value in sorted(candidate, key=str)],
                )
        return True, False

    def find_receipt(self, idempotency_key: str):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT command_fingerprint,staff_id,outcome,review_identity "
                "FROM staff_historical_adoption_receipts WHERE idempotency_key=%s FOR UPDATE",
                (idempotency_key,),
            )
            return cursor.fetchone()

    def claim(self, key: str, command_fingerprint: str, source_identity: str) -> bool:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT IGNORE INTO application_command_claims "
                "(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) "
                "VALUES (%s,'staff_historical_adoption',%s,%s,%s)",
                (key, source_identity, command_fingerprint, key),
            )
            return int(cursor.rowcount) == 1

    def save_receipt(
        self,
        *,
        key: str,
        command_fingerprint: str,
        source_identity: str,
        source_fingerprint: str,
        preview_fingerprint: str,
        staff_id: int | None,
        outcome: str,
        changed_fields: dict[str, object],
        review_identity: str | None,
    ) -> None:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO staff_historical_adoption_receipts "
                "(idempotency_key,command_fingerprint,source_event_identity,source_fingerprint,"
                "preview_fingerprint,staff_id,outcome,changed_fields,review_identity) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    key,
                    command_fingerprint,
                    source_identity,
                    source_fingerprint,
                    preview_fingerprint,
                    staff_id,
                    outcome,
                    json.dumps(changed_fields, ensure_ascii=False, sort_keys=True),
                    review_identity,
                ),
            )


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _bank_tuple(row):
    return (row.get("bank_code"), row.get("branch_code"), str(row.get("account_no")), bool(row.get("is_primary")))


def _has_cross_staff_bank_collision(cursor, staff_id, candidate):
    account_numbers = tuple(sorted({str(value[2]) for value in candidate}))
    placeholders = ",".join("%s" for _ in account_numbers)
    cursor.execute(
        f"SELECT staff_id FROM staff_bank_accounts WHERE account_no IN ({placeholders}) FOR UPDATE",
        account_numbers,
    )
    return any(int(row["staff_id"]) != staff_id for row in cursor.fetchall())


def _relation_tuple(row, value_column, detail_column):
    values = [row.get(value_column)]
    if detail_column:
        values.append(row.get(detail_column))
    return tuple(values)


__all__ = ["MySqlStaffHistoricalAdoptionRepository"]

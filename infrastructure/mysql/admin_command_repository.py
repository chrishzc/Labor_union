from __future__ import annotations

import json


SOURCE_TABLE_PRIMARY_KEYS = {
    "clients": "id",
    "beclass_records": "id",
    "staff": "id",
}
SOURCE_TABLE_EDITABLE_COLUMNS = {
    "clients": frozenset({"name", "gender", "phone", "city", "address", "notes", "admin_notes", "reject_reason"}),
    "beclass_records": frozenset({"name", "email", "phone", "tel", "ext", "city", "zip_code", "address", "admin_notes"}),
    "staff": frozenset({"name", "phone", "tel", "tel_ext", "email", "city", "zip_code", "address", "birthday", "has_massage_cert", "weekly_rest_days", "service_regions", "special_skills", "care_babies"}),
}


class AdminCommandRepository:
    def __init__(self, connection):
        self._connection = connection

    def load_holiday(self, holiday_date, *, for_update=False):
        return self._load_one("SELECT holiday_name, is_double_pay_default FROM holidays WHERE holiday_date = %s", holiday_date, for_update)

    def load_client_name(self, case_no, *, for_update=False):
        return self._load_one("SELECT name FROM clients WHERE case_no = %s", case_no, for_update)

    def _load_one(self, statement, value, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(statement + suffix, (value,))
            return cursor.fetchone()

    def load_receipt(self, family, key):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT request_fingerprint, result_snapshot FROM admin_command_receipts WHERE command_family = %s AND idempotency_key = %s FOR UPDATE", (family, key))
            return cursor.fetchone()

    def save_receipt(self, family, key, request_fingerprint, preview_fingerprint, actor, reason, result):
        with self._connection.cursor() as cursor:
            cursor.execute("INSERT INTO admin_command_receipts (command_family, idempotency_key, request_fingerprint, preview_fingerprint, actor, reason, result_snapshot) VALUES (%s, %s, %s, %s, %s, %s, %s)", (family, key, request_fingerprint, preview_fingerprint, actor, reason, json.dumps(result, ensure_ascii=False)))

    def upsert_holiday(self, holiday_date, holiday_name, double_pay):
        with self._connection.cursor() as cursor:
            cursor.execute("INSERT INTO holidays (holiday_date, holiday_name, is_double_pay_default) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE holiday_name = VALUES(holiday_name), is_double_pay_default = VALUES(is_double_pay_default)", (holiday_date, holiday_name, double_pay))

    def delete_holiday(self, holiday_date):
        with self._connection.cursor() as cursor:
            cursor.execute("DELETE FROM holidays WHERE holiday_date = %s", (holiday_date,))

    def update_client_name(self, case_no, client_name):
        with self._connection.cursor() as cursor:
            cursor.execute("UPDATE clients SET name = %s WHERE case_no = %s", (client_name, case_no))

    def load_source_row(self, table, row_id, *, for_update=False):
        primary_key = SOURCE_TABLE_PRIMARY_KEYS.get(table)
        if primary_key is None:
            raise ValueError("source_table_not_editable")
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table} WHERE {primary_key}=%s" + suffix, (row_id,))
            return cursor.fetchone()

    def update_source_row(self, table, row_id, updates):
        primary_key = SOURCE_TABLE_PRIMARY_KEYS.get(table)
        if primary_key is None or not updates or any(not field.isidentifier() for field in updates):
            raise ValueError("source_update_invalid")
        protected_columns = set(updates) - SOURCE_TABLE_EDITABLE_COLUMNS[table]
        if protected_columns:
            raise ValueError("protected_source_field:" + ",".join(sorted(protected_columns)))
        assignments = ", ".join(f"{field}=%s" for field in updates)
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET {assignments} WHERE {primary_key}=%s",
                (*updates.values(), row_id),
            )

    def commit(self): self._connection.commit()

    def rollback(self): self._connection.rollback()

"""
File: staff_historical_workbook_repository.py
Description: 保存 Staff 歷史 workbook 的全檔 command claim 與 terminal receipt。
"""

from __future__ import annotations

import json
from hashlib import sha256


class MySqlStaffHistoricalWorkbookRepository:
    _FAMILY = "staff_historical_workbook_adoption"

    def __init__(self, connection) -> None:
        self._connection = connection

    def load_receipt(self, key: str):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT request_fingerprint,result_snapshot FROM admin_command_receipts WHERE command_family=%s AND idempotency_key=%s", (self._FAMILY, key))
            return cursor.fetchone()

    def acquire_lock(self, key: str) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s,5) AS acquired", (self.lock_name(key),))
            row = cursor.fetchone()
        return bool(row and row["acquired"] == 1)

    def release_lock(self, key: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (self.lock_name(key),))

    def claim(self, key: str, digest: str, correlation_id: str) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO application_command_claims (idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)", (key, self._FAMILY, digest, digest, correlation_id))
            created = cursor.rowcount == 1
            if not created:
                cursor.execute("SELECT command_family,command_fingerprint FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE", (key,))
                claim = cursor.fetchone()
                if claim is None or claim["command_family"] != self._FAMILY or claim["command_fingerprint"] != digest:
                    return "conflict"
        return "created" if created else "resume"

    def save_receipt(self, key: str, digest: str, actor: str, preview_fingerprint: str, result: dict[str, object]) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("INSERT INTO admin_command_receipts (command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)", (self._FAMILY, key, digest, preview_fingerprint, actor, "Staff historical workbook upload", json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)))

    @staticmethod
    def lock_name(key: str) -> str:
        return f"staff-upload:{sha256(key.encode('utf-8')).hexdigest()[:51]}"


__all__ = ["MySqlStaffHistoricalWorkbookRepository"]

"""
File: hcm_workbook_import_repository.py
Description: 保存HCM workbook command claim，並依identity或摘要讀取immutable receipt。
"""

from __future__ import annotations

import json
from hashlib import sha256


class HcmWorkbookImportRepository:
    """Case Import owns this adapter although it reuses global durable tables."""

    _FAMILY = "hcm_workbook_ingest"

    def __init__(self, connection) -> None:
        self._connection = connection

    def acquire_lock(self, key: str) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (self._lock_name(key),))
            row = cursor.fetchone()
        return bool(row and row["acquired"] == 1)

    def release_lock(self, key: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (self._lock_name(key),))

    @staticmethod
    def _lock_name(key: str) -> str:
        """MySQL user lock names are capped at 64 bytes; retain deterministic isolation."""
        return f"hcm-upload:{sha256(key.encode('utf-8')).hexdigest()[:52]}"

    def load_receipt(self, key: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s",
                (self._FAMILY, key),
            )
            return cursor.fetchone()

    def load_receipt_by_digest(self, digest: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND request_fingerprint=%s ORDER BY id ASC LIMIT 1",
                (self._FAMILY, digest),
            )
            return cursor.fetchone()

    def query_recent_receipts(self, *, limit: int, before_receipt_id: int | None):
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise ValueError("hcm_result_limit_invalid")
        predicate = "AND id<%s" if before_receipt_id is not None else ""
        parameters = (self._FAMILY, before_receipt_id, limit) if before_receipt_id is not None else (self._FAMILY, limit)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,request_fingerprint,result_snapshot,created_at "
                "FROM admin_command_receipts WHERE command_family=%s "
                f"{predicate} ORDER BY id DESC LIMIT %s",
                parameters,
            )
            return tuple(cursor.fetchall())

    def claim(self, key: str, digest: str, correlation_id: str) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO application_command_claims "
                "(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (key, self._FAMILY, digest, digest, correlation_id),
            )
            created = cursor.rowcount == 1
            if not created:
                cursor.execute(
                    "SELECT command_family,aggregate_identity,command_fingerprint "
                    "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
                    (key,),
                )
                claim = cursor.fetchone()
                if not claim or claim["command_family"] != self._FAMILY or claim["command_fingerprint"] != digest:
                    return "conflict"
        return "created" if created else "resume"

    def save_receipt(self, key: str, digest: str, actor: str, result: dict) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (self._FAMILY, key, digest, digest, actor, "HCM workbook upload", _json(result)),
            )


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

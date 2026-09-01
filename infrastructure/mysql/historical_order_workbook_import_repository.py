"""
File: historical_order_workbook_import_repository.py
Description: 保存訂單歷史 workbook 的 command claim 與 terminal receipt，避免整檔重複採納。
"""

from __future__ import annotations

from hashlib import sha256
import json


class HistoricalOrderWorkbookImportRepository:
    """Orders adapter over global durable command primitives."""

    _FAMILY = "historical_order_workbook_ingest"

    def __init__(self, connection) -> None:
        self._connection = connection

    def acquire_lock(self, key: str) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (self._lock_name(key),))
            return bool((row := cursor.fetchone()) and row["acquired"] == 1)

    def release_lock(self, key: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (self._lock_name(key),))

    def load_receipt(self, key: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s",
                (self._FAMILY, key),
            )
            return cursor.fetchone()

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
                    "SELECT command_family,command_fingerprint FROM application_command_claims "
                    "WHERE idempotency_key=%s FOR UPDATE",
                    (key,),
                )
                claim = cursor.fetchone()
                if not claim or claim["command_family"] != self._FAMILY or claim["command_fingerprint"] != digest:
                    return "conflict"
        return "created" if created else "resume"

    def save_receipt(self, key: str, digest: str, preview_fingerprint: str, actor: str, result: dict) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (self._FAMILY, key, digest, preview_fingerprint, actor, "訂單歷史資料匯入", _json(result)),
            )

    def find_open_review_identities(
        self, source_event_identities: tuple[str, ...]
    ) -> tuple[str, ...]:
        if not source_event_identities:
            return ()
        placeholders = ",".join("%s" for _ in source_event_identities)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT review.review_identity FROM historical_order_adoption_reviews review "
                "WHERE review.source_event_identity IN (" + placeholders + ") "
                "AND NOT EXISTS (SELECT 1 FROM historical_order_review_remediation_events remediation "
                "WHERE remediation.prior_review_identity=review.review_identity) "
                "ORDER BY review.id",
                source_event_identities,
            )
            rows = cursor.fetchall()
        return tuple(str(row["review_identity"]) for row in rows)

    @staticmethod
    def _lock_name(key: str) -> str:
        return f"order-history:{sha256(key.encode('utf-8')).hexdigest()[:50]}"


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

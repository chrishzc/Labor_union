"""MySQL adapter for LINE worker heartbeat and append-only security receipts."""

from __future__ import annotations

from typing import Any

from infrastructure.mysql.line_repository_support import aware_utc, database_utc, optional_row
from subsystems.line.runtime_contracts import (
    LineRuntimeMode,
    LineWebhookSecurityReceipt,
    LineWorkerHeartbeat,
)


class MySqlLineRuntimeRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def record_heartbeat(self, heartbeat: LineWorkerHeartbeat) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _UPSERT_HEARTBEAT_SQL,
                (
                    heartbeat.worker_identity,
                    heartbeat.process_id,
                    heartbeat.host_name,
                    heartbeat.runtime_mode.value,
                    heartbeat.component_status_json,
                    database_utc(heartbeat.last_cycle_at) if heartbeat.last_cycle_at else None,
                    database_utc(heartbeat.heartbeat_at),
                    database_utc(heartbeat.stopped_at) if heartbeat.stopped_at else None,
                    heartbeat.last_error_code,
                    heartbeat.last_error_message,
                ),
            )

    def latest_heartbeat(self) -> LineWorkerHeartbeat | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_LATEST_HEARTBEAT_SQL)
            row = optional_row(cursor.fetchone())
        return None if row is None else _heartbeat(row)

    def append_security_receipt(self, receipt: LineWebhookSecurityReceipt) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _INSERT_SECURITY_RECEIPT_SQL,
                (
                    receipt.request_fingerprint,
                    receipt.signature_present,
                    receipt.outcome.value,
                    receipt.event_count,
                    receipt.correlation_id,
                    database_utc(receipt.occurred_at),
                ),
            )

    def queue_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._connection.cursor() as cursor:
            for name, table in (
                ("inbox_pending", "line_inbox_events"),
                ("delivery_pending", "line_delivery_tasks"),
                ("legacy_pending", "line_tasks"),
            ):
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM {table} "
                    "WHERE processing_status='pending'"
                    if table != "line_tasks"
                    else "SELECT COUNT(*) AS total FROM line_tasks WHERE status='pending'"
                )
                row = optional_row(cursor.fetchone()) or {"total": 0}
                counts[name] = int(row["total"])
            cursor.execute(
                "SELECT "
                "SUM(processing_status IN ('pending','processing','retryable_failed')) AS active_total,"
                "SUM(processing_status='failed') AS failed_total "
                "FROM line_delivery_tasks "
                "WHERE source_aggregate_type='matching_notification_intent'"
            )
            matching = optional_row(cursor.fetchone()) or {}
            counts["matching_delivery_active"] = int(matching.get("active_total") or 0)
            counts["matching_delivery_failed"] = int(matching.get("failed_total") or 0)
        return counts


def _heartbeat(row: dict[str, object]) -> LineWorkerHeartbeat:
    return LineWorkerHeartbeat(
        str(row["worker_identity"]),
        int(row["process_id"]),
        str(row["host_name"]),
        LineRuntimeMode(str(row["runtime_mode"])),
        str(row["component_status_snapshot"]),
        aware_utc(row["heartbeat_at_utc"]),
        aware_utc(row["last_cycle_at_utc"]) if row.get("last_cycle_at_utc") else None,
        aware_utc(row["stopped_at_utc"]) if row.get("stopped_at_utc") else None,
        str(row["last_error_code"]) if row.get("last_error_code") else None,
        str(row["last_error_message"]) if row.get("last_error_message") else None,
    )


_UPSERT_HEARTBEAT_SQL = """
INSERT INTO line_worker_heartbeats (
    worker_identity,process_id,host_name,runtime_mode,component_status_snapshot,
    last_cycle_at_utc,heartbeat_at_utc,stopped_at_utc,last_error_code,last_error_message
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE process_id=VALUES(process_id),host_name=VALUES(host_name),
runtime_mode=VALUES(runtime_mode),component_status_snapshot=VALUES(component_status_snapshot),
last_cycle_at_utc=VALUES(last_cycle_at_utc),heartbeat_at_utc=VALUES(heartbeat_at_utc),
stopped_at_utc=VALUES(stopped_at_utc),last_error_code=VALUES(last_error_code),
last_error_message=VALUES(last_error_message)
"""
_LATEST_HEARTBEAT_SQL = (
    "SELECT worker_identity,process_id,host_name,runtime_mode,component_status_snapshot,"
    "last_cycle_at_utc,heartbeat_at_utc,stopped_at_utc,last_error_code,last_error_message "
    "FROM line_worker_heartbeats ORDER BY heartbeat_at_utc DESC LIMIT 1"
)
_INSERT_SECURITY_RECEIPT_SQL = """
INSERT INTO line_webhook_security_receipts (
    request_fingerprint,signature_present,verification_outcome,event_count,
    correlation_id,occurred_at_utc
) VALUES (%s,%s,%s,%s,%s,%s)
"""


__all__ = ["MySqlLineRuntimeRepository"]

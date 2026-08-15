"""
File: scheduling_checkpoint_notification_source_repository.py
Description: 保存 Scheduling checkpoint outbox 的投影成功或最多三次、一秒間隔的失敗狀態。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from infrastructure.mysql.line_repository_support import aware_utc, database_utc
from subsystems.line.scheduling_checkpoint_notification_source import SchedulingCheckpointOutboxItem


class MySqlSchedulingCheckpointNotificationSourceRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def claim_due(self, now: datetime, limit: int) -> tuple[SchedulingCheckpointOutboxItem, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_CLAIM_SQL, (database_utc(now), limit))
            rows = tuple(cursor.fetchall() or ())
        return tuple(_item(row) for row in rows)

    def mark_published(self, outbox_id: int) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_PUBLISH_SQL, (outbox_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("scheduling_checkpoint_outbox_state_conflict")

    def mark_retry_or_failed(self, outbox_id: int, now: datetime, error: Exception) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_FAIL_SQL, (database_utc(now + timedelta(seconds=1)), type(error).__name__[:128], outbox_id))
            if cursor.rowcount != 1:
                raise RuntimeError("scheduling_checkpoint_outbox_state_conflict")


def _item(row) -> SchedulingCheckpointOutboxItem:
    payload = json.loads(row["payload_snapshot"]) if isinstance(row["payload_snapshot"], str) else row["payload_snapshot"]
    if not isinstance(payload, dict):
        raise ValueError("scheduling_checkpoint_outbox_payload_invalid")
    return SchedulingCheckpointOutboxItem(
        int(row["id"]),
        int(row["event_id"]),
        payload,
        aware_utc(row["occurred_at_utc"]),
    )


_CLAIM_SQL = (
    "SELECT outbox.id,outbox.event_id,outbox.payload_snapshot,event.created_at_utc "
    "FROM scheduling_service_day_checkpoint_outbox outbox "
    "JOIN scheduling_service_day_checkpoint_events event ON event.id=outbox.event_id "
    "WHERE outbox.delivery_status='pending' AND (outbox.next_attempt_at_utc IS NULL OR outbox.next_attempt_at_utc<=%s) "
    "ORDER BY outbox.id LIMIT %s FOR UPDATE SKIP LOCKED"
)
_PUBLISH_SQL = (
    "UPDATE scheduling_service_day_checkpoint_outbox SET delivery_status='published',published_at_utc=UTC_TIMESTAMP(6),"
    "last_error_code=NULL WHERE id=%s AND delivery_status='pending'"
)
_FAIL_SQL = (
    "UPDATE scheduling_service_day_checkpoint_outbox SET delivery_status=IF(attempt_count+1>=3,'failed','pending'),"
    "attempt_count=attempt_count+1,next_attempt_at_utc=IF(attempt_count+1>=3,NULL,%s),last_error_code=%s "
    "WHERE id=%s AND delivery_status='pending'"
)


__all__ = ["MySqlSchedulingCheckpointNotificationSourceRepository"]

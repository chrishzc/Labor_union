"""
File: scheduling_rebuild_notification_invalidation_repository.py
Description: 保存排班重建通知失效投影，未知錯誤最多重試三次且每次間隔一秒。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from infrastructure.mysql.line_repository_support import database_utc
from subsystems.line.scheduling_rebuild_notification_invalidation import (
    SchedulingRebuildOutboxItem,
)


class MySqlSchedulingRebuildNotificationInvalidationRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def claim_due(
        self, now: datetime, limit: int
    ) -> tuple[SchedulingRebuildOutboxItem, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_CLAIM_SQL, (database_utc(now), limit))
            rows = tuple(cursor.fetchall() or ())
            for row in rows:
                cursor.execute(_CLAIM_UPDATE_SQL, (int(row["id"]),))
        return tuple(_item(row) for row in rows)

    def mark_published(self, outbox_id: int) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_PUBLISH_SQL, (outbox_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("scheduling_rebuild_notification_outbox_state_conflict")

    def mark_retry_or_failed(
        self, outbox_id: int, now: datetime, error: Exception
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _FAIL_SQL,
                (
                    database_utc(now + timedelta(seconds=1)),
                    type(error).__name__[:128],
                    outbox_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("scheduling_rebuild_notification_outbox_state_conflict")


def _item(row) -> SchedulingRebuildOutboxItem:
    payload = row["payload_snapshot"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assignment_ids = payload.get("cancelled_assignment_ids") if isinstance(payload, dict) else None
    if not isinstance(assignment_ids, list) or not assignment_ids:
        raise ValueError("scheduling_rebuild_notification_outbox_payload_invalid")
    normalized = tuple(int(value) for value in assignment_ids)
    if any(value <= 0 for value in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError("scheduling_rebuild_notification_outbox_payload_invalid")
    return SchedulingRebuildOutboxItem(int(row["id"]), normalized)


_CLAIM_SQL = (
    "SELECT id,payload_snapshot FROM scheduling_rebuild_notification_outbox "
    "WHERE delivery_status='pending' AND (next_attempt_at_utc IS NULL OR next_attempt_at_utc<=%s) "
    "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"
)
_CLAIM_UPDATE_SQL = (
    "UPDATE scheduling_rebuild_notification_outbox SET delivery_status='processing' "
    "WHERE id=%s AND delivery_status='pending'"
)
_PUBLISH_SQL = (
    "UPDATE scheduling_rebuild_notification_outbox SET delivery_status='published',"
    "published_at_utc=UTC_TIMESTAMP(6),last_error_code=NULL "
    "WHERE id=%s AND delivery_status='processing'"
)
_FAIL_SQL = (
    "UPDATE scheduling_rebuild_notification_outbox "
    "SET delivery_status=IF(attempt_count+1>=3,'failed','pending'),"
    "attempt_count=attempt_count+1,next_attempt_at_utc=IF(attempt_count+1>=3,NULL,%s),"
    "last_error_code=%s WHERE id=%s AND delivery_status='processing'"
)


__all__ = ["MySqlSchedulingRebuildNotificationInvalidationRepository"]

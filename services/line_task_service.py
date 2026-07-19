"""Creation helpers for reliable LINE tasks."""

import json
import uuid
from datetime import datetime


def enqueue_line_task(
    cursor,
    *,
    to_user_id: str,
    message_content: str | None = None,
    task_type: str = "line_push",
    payload: dict | None = None,
    scheduled_at: datetime | None = None,
    source_event_id: str | None = None,
    idempotency_key: str | None = None,
) -> int | None:
    retry_key = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT IGNORE INTO line_tasks (
            to_user_id, task_type, message_content, payload_json, scheduled_at,
            source_event_id, idempotency_key, line_request_id
        ) VALUES (%s,%s,%s,%s,COALESCE(%s,UTC_TIMESTAMP()),%s,%s,%s)
        """,
        (
            to_user_id, task_type, message_content,
            json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            scheduled_at, source_event_id, idempotency_key, retry_key,
        ),
    )
    return cursor.lastrowid or None

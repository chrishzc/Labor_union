"""LINE push task worker.

The database is the source of truth.  ``wake_worker`` only shortens the wait;
tasks remain recoverable after an application restart.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

import pymysql
import requests

from services.db_service import get_connection as get_db_connection


_wakeup_event = asyncio.Event()


def wake_worker() -> None:
    """Wake the in-process worker after a task has been committed."""
    _wakeup_event.set()


def _seconds_until(next_run_at: datetime | None) -> float:
    if next_run_at is None:
        return 60.0
    return max(0.0, (next_run_at - datetime.now()).total_seconds())


def _load_due_tasks() -> list[dict[str, Any]]:
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM line_tasks
                WHERE status = 'pending'
                  AND scheduled_at <= NOW()
                ORDER BY scheduled_at ASC, id ASC
                LIMIT 5
                """
            )
            return list(cursor.fetchall())
    finally:
        conn.close()


def _load_next_run_at() -> datetime | None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT MIN(scheduled_at)
                FROM line_tasks
                WHERE status = 'pending'
                """
            )
            row = cursor.fetchone()
            if not row:
                return None
            if isinstance(row, dict):
                return next(iter(row.values()), None)
            return row[0]
    finally:
        conn.close()


def _send_task(task: dict[str, Any]) -> tuple[bool, str]:
    line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "mock_token")
    task_id = task["id"]

    if not line_token or line_token == "mock_token":
        print(f"[LINE Mock] Sent message successfully for Task ID: {task_id}")
        return True, ""

    try:
        response = requests.post(
            "https://api.line.me/v2/bot/message/push",
            json={
                "to": task["to_user_id"],
                "messages": [{"type": "text", "text": task["message_content"]}],
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {line_token}",
            },
            timeout=5,
        )
    except Exception as exc:
        return False, str(exc)

    if response.status_code == 200:
        return True, ""
    return False, f"HTTP {response.status_code}: {response.text}"


async def process_due_tasks() -> None:
    """Send every currently due batch without blocking the event loop."""
    while True:
        tasks = await asyncio.to_thread(_load_due_tasks)
        if not tasks:
            return

        for task in tasks:
            success, error = await asyncio.to_thread(_send_task, task)
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE line_tasks SET status = %s WHERE id = %s",
                        ("sent" if success else "failed", task["id"]),
                    )
                    conn.commit()
            finally:
                conn.close()

            if not success:
                print(f"[LINE Worker] Task #{task['id']} failed: {error}")


async def worker_loop() -> None:
    """Wait for a new-task notification or for the nearest schedule time."""
    print("[LINE Worker] Worker started")
    while True:
        try:
            await process_due_tasks()

            # Clear before querying. If a producer commits during the query it
            # sets the event again and the check below immediately reloops.
            _wakeup_event.clear()
            next_run_at = await asyncio.to_thread(_load_next_run_at)
            if _wakeup_event.is_set():
                continue

            timeout = _seconds_until(next_run_at)
            try:
                await asyncio.wait_for(_wakeup_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[LINE Worker] Worker loop error: {exc}")
            await asyncio.sleep(5)


def start_worker() -> asyncio.Task[None]:
    return asyncio.create_task(worker_loop(), name="line-task-worker")


async def stop_worker(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

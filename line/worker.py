"""
================================================================================
檔案名稱: line/worker.py
功能說明: LINE 背景任務 Worker，負責排程喚醒、任務鎖定、訊息發送、失敗重試與執行紀錄
================================================================================
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from functools import lru_cache
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import pymysql
import requests

from infrastructure.mysql.mysql_adapter import get_connection as get_db_connection
from infrastructure.line.redis_wakeup import RedisLineWakeupPublisher
from subsystems.line.rich_menu_publication_workflow import (
    import_legacy_rich_menu_ids,
    next_publication_run_at,
    process_due_publications,
    recover_stale_publications,
)


_wakeup_event = asyncio.Event()
_worker_task: asyncio.Task[None] | None = None
RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def wake_worker() -> None:
    _wakeup_event.set()
    publisher = _redis_wakeup_publisher()
    if publisher is None:
        return
    try:
        publisher.publish()
    except Exception as exc:
        print(f"[LINE Worker] Redis wake signal failed; DB fallback remains active: {exc}")


def wake_local_worker() -> None:
    """Wake only the legacy loop in this process without republishing."""
    _wakeup_event.set()


@lru_cache(maxsize=1)
def _redis_wakeup_publisher():
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
    return RedisLineWakeupPublisher(redis_url) if redis_url else None


def _recover_stale_tasks() -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE line_tasks
                SET status='pending', processing_started_at=NULL,
                    error_code='stale_recovered'
                WHERE status='processing'
                  AND processing_started_at < UTC_TIMESTAMP() - INTERVAL 10 MINUTE
                """
            )
            conn.commit()
    finally:
        conn.close()


def _claim_due_tasks(limit: int = 10) -> list[dict[str, Any]]:
    conn = get_db_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT * FROM line_tasks
                WHERE status='pending'
                  AND scheduled_at <= UTC_TIMESTAMP()
                  AND (next_retry_at IS NULL OR next_retry_at <= UTC_TIMESTAMP())
                ORDER BY scheduled_at, id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            )
            tasks = list(cursor.fetchall())
            if tasks:
                for task in tasks:
                    if not task.get("line_request_id"):
                        task["line_request_id"] = str(uuid.uuid4())
                ids = [task["id"] for task in tasks]
                placeholders = ",".join(["%s"] * len(ids))
                cursor.execute(
                    f"UPDATE line_tasks SET status='processing', processing_started_at=UTC_TIMESTAMP() WHERE id IN ({placeholders})",
                    ids,
                )
                for task in tasks:
                    cursor.execute(
                        "UPDATE line_tasks SET line_request_id=COALESCE(line_request_id,%s) WHERE id=%s",
                        (task["line_request_id"], task["id"]),
                    )
        conn.commit()
        return tasks
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _next_run_at() -> datetime | None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT MIN(GREATEST(scheduled_at, COALESCE(next_retry_at, scheduled_at)))
                FROM line_tasks WHERE status='pending'
                """
            )
            row = cursor.fetchone()
            return next(iter(row.values()), None) if isinstance(row, dict) else row[0] if row else None
    finally:
        conn.close()


def _line_headers(task: dict[str, Any]) -> dict[str, str]:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "mock_token")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Line-Retry-Key": task["line_request_id"],
    }


def _push_text(task: dict[str, Any], text: str) -> tuple[bool, bool, str, str]:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "mock_token")
    if not token or token == "mock_token":
        print(f"[LINE Mock] Task #{task['id']}: {task['task_type']}")
        return True, False, "", ""
    try:
        response = requests.post(
            "https://api.line.me/v2/bot/message/push",
            json={"to": task["to_user_id"], "messages": [{"type": "text", "text": text}]},
            headers=_line_headers(task),
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, True, "network_error", str(exc)
    if response.status_code == 200:
        return True, False, "", ""
    return False, response.status_code in RETRYABLE_HTTP, f"http_{response.status_code}", response.text


def _matching_willingness_actions(
    case_no: str,
    plan_id: int,
    segment_id: int,
) -> list[dict[str, str]]:
    return [
        {
            "type": "postback",
            "label": label,
            "data": urlencode(
                {
                    "action": willingness,
                    "case_no": case_no,
                    "plan_id": plan_id,
                    "segment_id": segment_id,
                }
            ),
        }
        for willingness, label in (("willing", "願意接案"), ("unwilling", "暫不考慮"))
    ]


def _matching_willingness_message(task: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(task.get("payload_json") or "{}")
    case_no = str(payload["case_no"]).strip()
    plan_id = int(payload["plan_id"])
    segment_id = int(payload["segment_id"])
    if not case_no or plan_id <= 0 or segment_id <= 0:
        raise ValueError("Invalid canonical matching identity")
    return {
        "type": "template",
        "altText": "媒合意願確認",
        "template": {
            "type": "buttons",
            "text": task.get("message_content") or "請確認是否願意接案。",
            "actions": _matching_willingness_actions(case_no, plan_id, segment_id),
        },
    }


def _push_matching_willingness_card(
    task: dict[str, Any],
) -> tuple[bool, bool, str, str]:
    try:
        message = _matching_willingness_message(task)
    except (KeyError, TypeError, ValueError) as exc:
        return False, False, "invalid_matching_payload", str(exc)
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "mock_token")
    if not token or token == "mock_token":
        return True, False, "", ""
    try:
        response = requests.post(
            "https://api.line.me/v2/bot/message/push",
            json={"to": task["to_user_id"], "messages": [message]},
            headers=_line_headers(task),
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, True, "network_error", str(exc)
    if response.status_code == 200:
        return True, False, "", ""
    return False, response.status_code in RETRYABLE_HTTP, f"http_{response.status_code}", response.text


def _menu_action(task: dict[str, Any], link: bool) -> tuple[bool, bool, str, str]:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "mock_token")
    payload = json.loads(task.get("payload_json") or "{}")
    if not token or token == "mock_token":
        return True, False, "", ""
    url = f"https://api.line.me/v2/bot/user/{task['to_user_id']}/richmenu"
    menu_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        if link:
            menu_id = payload.get("rich_menu_id")
            if not menu_id:
                return False, False, "menu_not_set", "Rich Menu ID is missing"
            response = requests.post(f"{url}/{menu_id}", headers=menu_headers, timeout=10)
        else:
            response = requests.delete(url, headers=menu_headers, timeout=10)
    except requests.RequestException as exc:
        return False, True, "network_error", str(exc)
    if response.status_code == 200:
        followup = payload.get("success_message")
        return _push_text(task, followup) if followup else (True, False, "", "")
    return False, response.status_code in RETRYABLE_HTTP, f"http_{response.status_code}", response.text


def _execute_task(task: dict[str, Any]) -> tuple[bool, bool, str, str]:
    task_type = task["task_type"]
    if task_type == "line_push":
        return _push_text(task, task.get("message_content") or "")
    if task_type == "matching_willingness_card":
        return _push_matching_willingness_card(task)
    if task_type == "rag_reply":
        return False, False, "legacy_rag_retired", "Use canonical Knowledge Retrieval worker"
    if task_type == "rich_menu_link":
        return _menu_action(task, True)
    if task_type == "rich_menu_unlink":
        return _menu_action(task, False)
    return False, False, "unknown_task_type", task_type


def _start_task_attempt(task: dict[str, Any]) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(attempt_no),0)+1 AS attempt_no FROM line_task_attempts WHERE task_id=%s",
                (task["id"],),
            )
            row = cursor.fetchone()
            attempt_no = int(row.get("attempt_no", 1) if isinstance(row, dict) else row[0])
            cursor.execute(
                """
                INSERT INTO line_task_attempts (
                    task_id, attempt_no, outcome, line_request_id
                ) VALUES (%s,%s,'running',%s)
                """,
                (task["id"], attempt_no, task.get("line_request_id")),
            )
            attempt_id = int(cursor.lastrowid)
        conn.commit()
        return attempt_id
    finally:
        conn.close()


def _finish_task_attempt(
    attempt_id: int,
    result: tuple[bool, bool, str, str],
    final_status: str,
) -> None:
    _, retryable, code, message = result
    outcome = {
        "sent": "sent",
        "pending": "retry_scheduled",
        "failed": "failed",
    }[final_status]
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE line_task_attempts
                SET outcome=%s, retryable=%s, error_code=%s,
                    error_message=%s, finished_at=UTC_TIMESTAMP()
                WHERE id=%s
                """,
                (
                    outcome,
                    retryable,
                    code or None,
                    message[:4000] if message else None,
                    attempt_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _finish_task(task: dict[str, Any], result: tuple[bool, bool, str, str]) -> str:
    success, retryable, code, message = result
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if success:
                cursor.execute(
                    "UPDATE line_tasks SET status='sent', sent_at=UTC_TIMESTAMP(), processing_started_at=NULL, error_code=NULL, error_message=NULL WHERE id=%s",
                    (task["id"],),
                )
                final_status = "sent"
            elif retryable and task["retry_count"] < task["max_retries"]:
                retry_count = task["retry_count"] + 1
                delay_seconds = min(60 * (2 ** (retry_count - 1)), 3600)
                cursor.execute(
                    """
                    UPDATE line_tasks SET status='pending', retry_count=%s,
                        next_retry_at=DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND),
                        processing_started_at=NULL, error_code=%s, error_message=%s
                    WHERE id=%s
                    """,
                    (retry_count, delay_seconds, code, message[:4000], task["id"]),
                )
                final_status = "pending"
            else:
                cursor.execute(
                    """
                    UPDATE line_tasks SET status='failed', failed_at=UTC_TIMESTAMP(),
                        processing_started_at=NULL, error_code=%s, error_message=%s
                    WHERE id=%s
                    """,
                    (code, message[:4000], task["id"]),
                )
                final_status = "failed"
            conn.commit()
            return final_status
    finally:
        conn.close()


async def process_due_tasks() -> None:
    while True:
        tasks = await asyncio.to_thread(_claim_due_tasks)
        if not tasks:
            return
        for task in tasks:
            attempt_id = await asyncio.to_thread(_start_task_attempt, task)
            try:
                result = await asyncio.to_thread(_execute_task, task)
            except Exception as exc:
                result = (False, True, "worker_exception", str(exc))
            final_status = await asyncio.to_thread(_finish_task, task, result)
            await asyncio.to_thread(
                _finish_task_attempt, attempt_id, result, final_status
            )


async def worker_loop() -> None:
    print("[LINE Worker] Reliable worker started")
    imported = await asyncio.to_thread(import_legacy_rich_menu_ids)
    if imported:
        print(f"[LINE Worker] Imported {imported} legacy Rich Menu ID(s)")
    await asyncio.to_thread(_recover_stale_tasks)
    await asyncio.to_thread(recover_stale_publications)
    while True:
        try:
            await process_due_tasks()
            await asyncio.to_thread(process_due_publications)
            _wakeup_event.clear()
            next_at = await asyncio.to_thread(_next_run_at)
            next_publication_at = await asyncio.to_thread(next_publication_run_at)
            if next_at is None or (
                next_publication_at is not None and next_publication_at < next_at
            ):
                next_at = next_publication_at
            if _wakeup_event.is_set():
                continue
            # Notification is primary; a low-frequency scan recovers a task if
            # its wake-up signal was lost while a process was restarting.
            timeout = 60.0 if next_at is None else min(
                60.0,
                max(0.0, (next_at - _utc_now_naive()).total_seconds()),
            )
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
    global _worker_task
    _worker_task = asyncio.create_task(worker_loop(), name="line-task-worker")
    return _worker_task


def worker_is_running() -> bool:
    return _worker_task is not None and not _worker_task.done()


async def stop_worker(task: asyncio.Task[None]) -> None:
    global _worker_task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        if _worker_task is task:
            _worker_task = None

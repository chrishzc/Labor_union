"""Reliable LINE task worker with scheduling, locking and retries."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import pymysql
import requests

from services.db_service import get_connection as get_db_connection


_wakeup_event = asyncio.Event()
RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def wake_worker() -> None:
    _wakeup_event.set()


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


def _rag_answer(user_text: str) -> str:
    fallback = "很抱歉，我不太懂您的意思，已經幫您轉交給行政專員為您人工處理。"
    try:
        import chromadb

        client = chromadb.PersistentClient(path="./db/chroma_data")
        collection = client.get_or_create_collection("union_faq")
        results = collection.query(query_texts=[user_text], n_results=1)
        if results and results.get("distances") and results["distances"][0]:
            if results["distances"][0][0] < 1.0:
                return results["metadatas"][0][0].get("answer", fallback)
    except Exception as exc:
        print(f"[LINE Worker] RAG query failed: {exc}")
    return fallback


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
    if task_type == "rag_reply":
        payload = json.loads(task.get("payload_json") or "{}")
        return _push_text(task, _rag_answer(payload.get("user_text", "")))
    if task_type == "rich_menu_link":
        return _menu_action(task, True)
    if task_type == "rich_menu_unlink":
        return _menu_action(task, False)
    return False, False, "unknown_task_type", task_type


def _finish_task(task: dict[str, Any], result: tuple[bool, bool, str, str]) -> None:
    success, retryable, code, message = result
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if success:
                cursor.execute(
                    "UPDATE line_tasks SET status='sent', sent_at=UTC_TIMESTAMP(), processing_started_at=NULL, error_code=NULL, error_message=NULL WHERE id=%s",
                    (task["id"],),
                )
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
            else:
                cursor.execute(
                    """
                    UPDATE line_tasks SET status='failed', failed_at=UTC_TIMESTAMP(),
                        processing_started_at=NULL, error_code=%s, error_message=%s
                    WHERE id=%s
                    """,
                    (code, message[:4000], task["id"]),
                )
            conn.commit()
    finally:
        conn.close()


async def process_due_tasks() -> None:
    while True:
        tasks = await asyncio.to_thread(_claim_due_tasks)
        if not tasks:
            return
        for task in tasks:
            result = await asyncio.to_thread(_execute_task, task)
            await asyncio.to_thread(_finish_task, task, result)


async def worker_loop() -> None:
    print("[LINE Worker] Reliable worker started")
    await asyncio.to_thread(_recover_stale_tasks)
    while True:
        try:
            await process_due_tasks()
            _wakeup_event.clear()
            next_at = await asyncio.to_thread(_next_run_at)
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
    return asyncio.create_task(worker_loop(), name="line-task-worker")


async def stop_worker(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

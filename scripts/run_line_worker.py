"""Start the independently restartable canonical and/or legacy LINE worker."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from infrastructure.line.redis_wakeup import (
    RedisLineWakeupSubscriber,
    SleepingLineWakeupSubscriber,
)
from infrastructure.mysql.line_runtime_repository import MySqlLineRuntimeRepository
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from line.worker import process_due_tasks, wake_local_worker, worker_loop
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.event_dispatcher import LineEventDispatcher
from subsystems.line.runtime_contracts import LineRuntimeMode, LineWorkerHeartbeat
from subsystems.line.webhook_event_consumer import LineWebhookEventConsumer
from subsystems.line.worker_runtime import CanonicalLineWorkerRuntime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def main() -> int:
    arguments = _arguments()
    mode = LineRuntimeMode(arguments.mode)
    _require_compatible_runtime_modes(mode)
    worker_identity = arguments.worker_id or _default_worker_identity()
    if arguments.once:
        _run_once(mode, worker_identity)
        return 0
    if mode is LineRuntimeMode.CANONICAL:
        try:
            _canonical_runtime(worker_identity, arguments.poll_seconds).run_forever()
        except KeyboardInterrupt:
            _record_heartbeat(worker_identity, mode, None, stopped=True)
        return 0
    asyncio.run(_run_legacy_runtime(mode, worker_identity, arguments.poll_seconds))
    return 0


def _run_once(mode: LineRuntimeMode, worker_identity: str) -> None:
    if mode is not LineRuntimeMode.LEGACY:
        _canonical_runtime(worker_identity, 60.0).run_once()
    if mode is not LineRuntimeMode.CANONICAL:
        asyncio.run(process_due_tasks())


async def _run_legacy_runtime(
    mode: LineRuntimeMode,
    worker_identity: str,
    poll_seconds: float,
) -> None:
    stop_event = threading.Event()
    canonical_task = None
    if mode is LineRuntimeMode.COMPATIBILITY:
        runtime = _canonical_runtime(worker_identity, poll_seconds)
        canonical_task = asyncio.create_task(asyncio.to_thread(runtime.run_forever, stop_event))
    bridge_task = asyncio.create_task(_redis_legacy_wakeup_bridge())
    heartbeat_task = asyncio.create_task(_legacy_heartbeat_loop(worker_identity, mode))
    try:
        await worker_loop()
    finally:
        stop_event.set()
        for task in (bridge_task, heartbeat_task, canonical_task):
            if task is not None:
                task.cancel()
        await asyncio.to_thread(
            _record_heartbeat,
            worker_identity,
            mode,
            None,
            True,
        )


async def _redis_legacy_wakeup_bridge() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
    if not redis_url:
        return
    subscriber = RedisLineWakeupSubscriber(redis_url)
    try:
        while True:
            if await asyncio.to_thread(subscriber.wait, 60.0):
                wake_local_worker()
    finally:
        subscriber.close()


async def _legacy_heartbeat_loop(worker_identity: str, mode: LineRuntimeMode) -> None:
    while True:
        try:
            await asyncio.to_thread(_record_heartbeat, worker_identity, mode, None)
        except Exception as error:
            print(f"[LINE Worker] Heartbeat unavailable: {error}")
        await asyncio.sleep(15.0)


def _canonical_runtime(worker_identity: str, poll_seconds: float):
    now = lambda: datetime.now(timezone.utc)
    event_consumer = LineWebhookEventConsumer(
        open_line_unit_of_work,
        LineEventDispatcher(),
        worker_identity,
        now,
    )
    delivery_worker = LineDeliveryWorker(
        open_line_unit_of_work,
        LineMessagingApiAdapter(_required_access_token()),
        worker_identity,
        now,
    )
    return CanonicalLineWorkerRuntime(
        event_consumer,
        delivery_worker,
        _wakeup_subscriber(),
        _next_due_at,
        lambda heartbeat: _write_heartbeat(heartbeat),
        worker_identity,
        poll_seconds,
    )


def _next_due_at():
    with open_line_unit_of_work() as unit_of_work:
        due_times = (
            unit_of_work.webhook_inbox.next_due_at(),
            unit_of_work.delivery_tasks.next_due_at(),
        )
        unit_of_work.commit()
    available = tuple(due_at for due_at in due_times if due_at is not None)
    return min(available) if available else None


def _wakeup_subscriber():
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
    if redis_url:
        return RedisLineWakeupSubscriber(redis_url)
    return SleepingLineWakeupSubscriber()


def _record_heartbeat(
    worker_identity,
    mode,
    error: Exception | None,
    stopped: bool = False,
) -> None:
    now = datetime.now(timezone.utc)
    heartbeat = LineWorkerHeartbeat(
        worker_identity,
        os.getpid(),
        socket.gethostname(),
        mode,
        json.dumps({"legacy_delivery": "running"}, separators=(",", ":")),
        now,
        last_cycle_at=now,
        stopped_at=now if stopped else None,
        last_error_code=type(error).__name__ if error else None,
        last_error_message=str(error)[:1000] if error else None,
    )
    _write_heartbeat(heartbeat)


def _write_heartbeat(heartbeat: LineWorkerHeartbeat) -> None:
    connection = get_connection()
    try:
        connection.begin()
        MySqlLineRuntimeRepository(connection).record_heartbeat(heartbeat)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _required_access_token() -> str:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token or token in {"mock_token", "your_line_channel_access_token_here"}:
        raise RuntimeError("canonical LINE worker requires a real access token")
    return token


def _require_compatible_runtime_modes(worker_mode: LineRuntimeMode) -> None:
    webhook_value = os.getenv("LINE_WEBHOOK_RUNTIME_MODE", "legacy").strip().lower()
    try:
        webhook_mode = LineRuntimeMode(webhook_value)
    except ValueError as error:
        raise RuntimeError("invalid LINE_WEBHOOK_RUNTIME_MODE") from error
    if worker_mode is LineRuntimeMode.COMPATIBILITY:
        return
    if worker_mode is not webhook_mode:
        raise RuntimeError(
            "LINE worker and webhook runtime modes must match unless worker uses compatibility"
        )


def _default_worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run independent LINE workers.")
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in LineRuntimeMode),
        default=os.getenv("LINE_WORKER_RUNTIME_MODE", "legacy"),
    )
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())

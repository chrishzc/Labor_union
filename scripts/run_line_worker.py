"""Start the independently restartable canonical and/or legacy LINE worker."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import threading
from urllib.parse import urlencode
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from infrastructure.line.media_adapters import (
    FileSystemLineMediaObjectStore,
    LineMediaApiAdapter,
)
from infrastructure.line.rich_menu_api_adapter import LineRichMenuApiAdapter
from infrastructure.line.rich_menu_image_store import FileSystemRichMenuImageStore
from infrastructure.line.redis_wakeup import (
    RedisLineWakeupSubscriber,
    SleepingLineWakeupSubscriber,
)
from infrastructure.mysql.line_runtime_repository import MySqlLineRuntimeRepository
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.follow_schedule_application import enqueue_follow_schedule
from subsystems.line.media_application import (
    LineMediaArchiveWorker,
    schedule_line_media_archive,
)
from subsystems.line.order_group_application import LineOrderGroupApplication
from subsystems.line.runtime_alert_application import register_group_alert_target
from domains.line.media import LineMediaPolicy
from subsystems.line.event_dispatcher import LineEventDispatcher
from subsystems.line.runtime_contracts import LineRuntimeMode, LineWorkerHeartbeat
from subsystems.line.runtime_cutover import validate_line_worker_runtime
from subsystems.line.rich_menu_worker import LineRichMenuWorker
from subsystems.line.rich_menu_binding import (
    LineRichMenuBindingWorker,
    RICH_MENU_BINDING_INTENT,
)
from subsystems.line.webhook_event_consumer import LineWebhookEventConsumer
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers
from subsystems.line.matching_postback_application import (
    LineMatchingPostbackApplication,
)
from subsystems.line.knowledge_question_application import (
    enqueue_line_knowledge_question,
)
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.menu_command_application import LineMenuCommandApplication
from subsystems.line.identity_management_application import (
    IDENTITY_MENU_RESET_INTENT,
)
from subsystems.line.identity_revocation_worker import LineIdentityRevocationWorker
from subsystems.scheduling.matching_notification_application import (
    MatchingNotificationApplication,
)
from subsystems.line.worker_runtime import CanonicalLineWorkerRuntime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def main() -> int:
    arguments = _arguments()
    os.environ["LINE_WORKER_RUNTIME_MODE"] = arguments.mode
    mode = validate_line_worker_runtime(os.environ).worker_mode
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
        from line.worker import process_due_tasks

        asyncio.run(process_due_tasks())


async def _run_legacy_runtime(
    mode: LineRuntimeMode,
    worker_identity: str,
    poll_seconds: float,
) -> None:
    from line.worker import worker_loop

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
    from line.worker import wake_local_worker

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
        LineEventDispatcher(
            LineWebhookIdentityHandlers(
                now,
                _identity_flow_url,
                follow_scheduler=enqueue_follow_schedule,
                media_scheduler=schedule_line_media_archive,
                group_application=LineOrderGroupApplication(
                    now,
                    alert_group_registrar=register_group_alert_target,
                ),
                matching_postback_application=LineMatchingPostbackApplication(
                    MatchingNotificationApplication(open_line_unit_of_work, now)
                ),
                knowledge_question_scheduler=enqueue_line_knowledge_question,
                service_help_application=LineServiceHelpApplication(now, _identity_flow_url),
                menu_command_application=LineMenuCommandApplication(),
            ).registry()
        ),
        worker_identity,
        now,
    )
    delivery_worker = LineDeliveryWorker(
        open_line_unit_of_work,
        LineMessagingApiAdapter(_required_access_token()),
        worker_identity,
        now,
    )
    rich_menu_images = FileSystemRichMenuImageStore(_media_storage_root())
    rich_menu_provider = LineRichMenuApiAdapter(
        _required_access_token(),
        rich_menu_images.load,
    )
    rich_menu_worker = LineRichMenuWorker(
        open_line_unit_of_work,
        rich_menu_provider,
        rich_menu_images.materialize,
        worker_identity,
        now,
    )
    rich_menu_binding_worker = LineRichMenuBindingWorker(
        open_line_unit_of_work,
        rich_menu_provider,
        worker_identity,
        now,
    )
    identity_revocation_worker = LineIdentityRevocationWorker(
        open_line_unit_of_work,
        rich_menu_provider,
        worker_identity,
        now,
    )
    media_worker = LineMediaArchiveWorker(
        open_line_unit_of_work,
        LineMediaApiAdapter(_required_access_token()),
        FileSystemLineMediaObjectStore(_media_storage_root()),
        worker_identity,
        now,
        policy=LineMediaPolicy(
            (
                "application/pdf",
                "audio/m4a",
                "audio/mp4",
                "image/gif",
                "image/jpeg",
                "image/png",
                "image/webp",
                "video/mp4",
            ),
            int(os.getenv("LINE_MEDIA_MAX_BYTES", str(10 * 1024 * 1024))),
        ),
    )
    return CanonicalLineWorkerRuntime(
        event_consumer,
        delivery_worker,
        _wakeup_subscriber(),
        _next_due_at,
        lambda heartbeat: _write_heartbeat(heartbeat),
        worker_identity,
        poll_seconds,
        {
            "media_archives": media_worker,
            "rich_menu_publications": rich_menu_worker,
            "rich_menu_bindings": rich_menu_binding_worker,
            "identity_revocations": identity_revocation_worker,
        },
    )


def _next_due_at():
    with open_line_unit_of_work() as unit_of_work:
        due_times = (
            unit_of_work.webhook_inbox.next_due_at(),
            unit_of_work.delivery_tasks.next_due_at(),
            unit_of_work.rich_menu_publications.next_due_at(),
            unit_of_work.outbox.next_due_at(),
            unit_of_work.outbox.next_due_at(RICH_MENU_BINDING_INTENT),
            unit_of_work.outbox.next_due_at(IDENTITY_MENU_RESET_INTENT),
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


def _identity_flow_url(purpose: str, flow_id: str) -> str:
    query = urlencode({"purpose": purpose, "flow_id": flow_id})
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if liff_id and liff_id != "your_liff_id_here":
        return f"https://liff.line.me/{liff_id}/?{query}"
    base_url = _configured_public_base_url()
    if base_url:
        return f"{base_url}/line-identity?{query}"
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env == "production":
        raise RuntimeError("LINE identity flow requires LINE_LIFF_ID or LINE_PUBLIC_BASE_URL")
    return f"http://127.0.0.1:8000/line-identity?{query}"


def _configured_public_base_url() -> str:
    base_url = (
        os.getenv("LINE_PUBLIC_BASE_URL", "").strip()
        or os.getenv("BASE_URL", "").strip()
    ).rstrip("/")
    placeholders = {
        "https://your-public-domain.example",
        "https://your-domain.example.com",
    }
    return "" if base_url in placeholders else base_url


def _media_storage_root() -> Path:
    configured = os.getenv("MEDIA_STORAGE_ROOT", ".local_media").strip() or ".local_media"
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _default_worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run independent LINE workers.")
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in LineRuntimeMode),
        default=os.getenv("LINE_WORKER_RUNTIME_MODE", "canonical"),
    )
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())

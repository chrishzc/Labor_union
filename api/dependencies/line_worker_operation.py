"""
File: line_worker_operation.py
Description: 組合 canonical LINE worker 與已提交 Scheduling 通知來源的投影工作。
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from api.schemas.private_operations import WorkerRuntimeIdentity
from api.dependencies.runtime_heartbeat import record_runtime_heartbeat
from domains.line.media import LineMediaPolicy
from infrastructure.line.media_adapters import (
    FileSystemLineMediaObjectStore,
    LineMediaApiAdapter,
)
from infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from infrastructure.line.redis_wakeup import SleepingLineWakeupSubscriber
from infrastructure.line.rich_menu_api_adapter import LineRichMenuApiAdapter
from infrastructure.line.rich_menu_image_store import FileSystemRichMenuImageStore
from infrastructure.mysql.line_runtime_repository import MySqlLineRuntimeRepository
from infrastructure.mysql.line_notification_anomaly_worker import MySqlLineNotificationAnomalyWorker
from infrastructure.mysql.line_notification_reconciliation_worker import (
    MySqlLineNotificationReconciliationWorker,
)
from infrastructure.mysql.service_day_checkpoint_worker import MySqlServiceDayCheckpointWorker
from infrastructure.mysql.scheduling_checkpoint_notification_source_worker import (
    MySqlSchedulingCheckpointNotificationSourceWorker,
)
from infrastructure.mysql.scheduling_rebuild_notification_invalidation_worker import (
    MySqlSchedulingRebuildNotificationInvalidationWorker,
)
from infrastructure.mysql.service_day_log_notification_stop_worker import (
    MySqlServiceDayLogNotificationStopWorker,
)
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.event_dispatcher import LineEventDispatcher
from subsystems.line.follow_schedule_application import enqueue_follow_schedule
from subsystems.line.identity_management_application import IDENTITY_MENU_RESET_INTENT
from subsystems.line.identity_revocation_worker import LineIdentityRevocationWorker
from subsystems.line.knowledge_question_application import enqueue_line_knowledge_question
from subsystems.line.matching_postback_application import LineMatchingPostbackApplication
from subsystems.line.media_application import LineMediaArchiveWorker, schedule_line_media_archive
from subsystems.line.menu_command_application import LineMenuCommandApplication
from subsystems.line.order_group_application import LineOrderGroupApplication
from subsystems.line.rich_menu_binding import (
    RICH_MENU_BINDING_INTENT,
    LineRichMenuBindingWorker,
)
from subsystems.line.rich_menu_worker import LineRichMenuWorker
from subsystems.line.runtime_alert_application import register_group_alert_target
from subsystems.line.runtime_contracts import LineRuntimeMode, LineWorkerHeartbeat
from subsystems.line.runtime_cutover import validate_line_worker_runtime
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.webhook_event_consumer import LineWebhookEventConsumer
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers
from subsystems.line.worker_runtime import CanonicalLineWorkerRuntime
from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_line_cycle(
    worker_identity: str,
    runtime_identity: WorkerRuntimeIdentity,
) -> int:
    mode = validate_line_worker_runtime(os.environ).worker_mode
    processed = 0
    if mode is not LineRuntimeMode.LEGACY:
        processed += sum(_canonical_runtime(worker_identity, runtime_identity).run_once().values())
    if mode is not LineRuntimeMode.CANONICAL:
        from line.worker import process_due_tasks

        asyncio.run(process_due_tasks())
    record_runtime_heartbeat(runtime_identity, processed)
    return processed


# Keep provider and worker wiring together so one cycle's external-side-effect boundary is reviewable.
def _canonical_runtime(
    worker_identity: str,
    runtime_identity: WorkerRuntimeIdentity,
) -> CanonicalLineWorkerRuntime:
    now = lambda: datetime.now(timezone.utc)
    event_consumer = _event_consumer(worker_identity, now)
    delivery_worker = LineDeliveryWorker(
        open_line_unit_of_work,
        LineMessagingApiAdapter(_required_access_token()),
        worker_identity,
        now,
    )
    rich_menu_images = FileSystemRichMenuImageStore(_media_storage_root())
    rich_menu_provider = LineRichMenuApiAdapter(_required_access_token(), rich_menu_images.load)
    return CanonicalLineWorkerRuntime(
        event_consumer,
        delivery_worker,
        SleepingLineWakeupSubscriber(),
        _next_due_at,
        lambda heartbeat: _write_heartbeat(
            _heartbeat_from_caller(heartbeat, runtime_identity)
        ),
        worker_identity,
        60.0,
        _additional_workers(worker_identity, now, rich_menu_images, rich_menu_provider),
    )


def _event_consumer(worker_identity: str, now) -> LineWebhookEventConsumer:
    identity_handlers = LineWebhookIdentityHandlers(
        now,
        _identity_flow_url,
        follow_scheduler=enqueue_follow_schedule,
        media_scheduler=schedule_line_media_archive,
        group_application=LineOrderGroupApplication(now, alert_group_registrar=register_group_alert_target),
        matching_postback_application=LineMatchingPostbackApplication(
            MatchingNotificationApplication(open_line_unit_of_work, now)
        ),
        knowledge_question_scheduler=enqueue_line_knowledge_question,
        service_help_application=LineServiceHelpApplication(
            now,
            _identity_flow_url,
            LineMessagingApiAdapter(_required_access_token()),
        ),
        menu_command_application=LineMenuCommandApplication(),
    )
    return LineWebhookEventConsumer(
        open_line_unit_of_work,
        LineEventDispatcher(identity_handlers.registry()),
        worker_identity,
        now,
    )


def _additional_workers(worker_identity: str, now, images, provider) -> dict[str, object]:
    return {
        "service_day_checkpoints": MySqlServiceDayCheckpointWorker(get_connection, now),
        "service_day_checkpoint_notification_sources": MySqlSchedulingCheckpointNotificationSourceWorker(get_connection, now),
        "service_day_log_notification_stops": MySqlServiceDayLogNotificationStopWorker(get_connection, now),
        "scheduling_rebuild_notification_invalidations": MySqlSchedulingRebuildNotificationInvalidationWorker(get_connection, now),
        "notification_anomalies": MySqlLineNotificationAnomalyWorker(get_connection),
        "notification_reconciliation": MySqlLineNotificationReconciliationWorker(get_connection),
        "media_archives": LineMediaArchiveWorker(
            open_line_unit_of_work,
            LineMediaApiAdapter(_required_access_token()),
            FileSystemLineMediaObjectStore(_media_storage_root()),
            worker_identity,
            now,
            policy=_media_policy(),
        ),
        "rich_menu_publications": LineRichMenuWorker(
            open_line_unit_of_work,
            provider,
            images.materialize,
            worker_identity,
            now,
        ),
        "rich_menu_bindings": LineRichMenuBindingWorker(
            open_line_unit_of_work,
            provider,
            worker_identity,
            now,
        ),
        "identity_revocations": LineIdentityRevocationWorker(
            open_line_unit_of_work,
            provider,
            worker_identity,
            now,
        ),
    }


def _media_policy() -> LineMediaPolicy:
    return LineMediaPolicy(
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


def _heartbeat_from_caller(
    heartbeat: LineWorkerHeartbeat,
    identity: WorkerRuntimeIdentity,
) -> LineWorkerHeartbeat:
    return LineWorkerHeartbeat(
        heartbeat.worker_identity,
        identity.process_id,
        identity.hostname,
        heartbeat.runtime_mode,
        heartbeat.component_status_json,
        heartbeat.heartbeat_at,
        heartbeat.last_cycle_at,
        heartbeat.stopped_at,
        heartbeat.last_error_code,
        heartbeat.last_error_message,
    )




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
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        raise RuntimeError("LINE identity flow requires LINE_LIFF_ID or LINE_PUBLIC_BASE_URL")
    return f"http://127.0.0.1:8000/line-identity?{query}"


def _configured_public_base_url() -> str:
    base_url = (
        os.getenv("LINE_PUBLIC_BASE_URL", "").strip()
        or os.getenv("BASE_URL", "").strip()
    ).rstrip("/")
    placeholders = {"https://your-public-domain.example", "https://your-domain.example.com"}
    return "" if base_url in placeholders else base_url


def _media_storage_root() -> Path:
    configured = os.getenv("MEDIA_STORAGE_ROOT", ".local_media").strip() or ".local_media"
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path

"""
File: line_runtime.py
Description: 組合 LINE webhook、設定、通知規則管理與獨立 worker 的 runtime adapters。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache

from infrastructure.line.redis_wakeup import (
    NoopLineWakeupPublisher,
    RedisLineWakeupPublisher,
)
from infrastructure.line.signature_verifier import LineWebhookSignatureVerifier
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.line_runtime_repository import MySqlLineRuntimeRepository
from api.schemas.line_admin import (
    LegacyLineTaskCountsView,
    LineDatabaseHealthView,
    LineQueueCountsView,
    LineWorkerHealthView,
)
from subsystems.line.runtime_contracts import (
    LineRuntimeMode,
    LineWebhookVerificationOutcome,
)
from subsystems.line.runtime_cutover import validate_line_api_runtime
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.notification_rule_administration import (
    LineNotificationRuleAdministration,
)
from subsystems.line.notification_timeline_application import (
    LineNotificationTimelineApplication,
)
from subsystems.line.notification_manual_replay_application import (
    LineNotificationManualReplayApplication,
)
from subsystems.line.delivery_admin_application import (
    LineDeliveryTaskAdminApplication,
)
from subsystems.line.rich_menu_application import LineRichMenuApplication
from subsystems.line.order_group_application import LineOrderGroupQueryApplication
from subsystems.line.webhook_intake import LineWebhookIntake
from subsystems.line.runtime_alert_application import LineRuntimeApplication
from subsystems.line.runtime_health import classify_line_worker_health
from subsystems.line.feedback_application import LineFeedbackApplication


def line_webhook_runtime_mode() -> LineRuntimeMode:
    return validate_line_api_runtime(os.environ).webhook_mode


@lru_cache(maxsize=1)
def get_line_webhook_intake() -> LineWebhookIntake:
    channel_secret = os.getenv("LINE_CHANNEL_SECRET", "").strip()
    publisher = _wakeup_publisher()
    return LineWebhookIntake(
        LineWebhookSignatureVerifier(channel_secret),
        open_line_unit_of_work,
        publisher,
    )


@lru_cache(maxsize=1)
def get_line_configuration_application() -> LineConfigurationApplication:
    return LineConfigurationApplication(open_line_unit_of_work)


@lru_cache(maxsize=1)
def get_line_notification_rule_administration() -> LineNotificationRuleAdministration:
    return LineNotificationRuleAdministration(open_line_unit_of_work)


@lru_cache(maxsize=1)
def get_line_notification_timeline_application() -> LineNotificationTimelineApplication:
    return LineNotificationTimelineApplication(open_line_unit_of_work)


@lru_cache(maxsize=1)
def get_line_notification_manual_replay_application() -> LineNotificationManualReplayApplication:
    return LineNotificationManualReplayApplication(
        open_line_unit_of_work, lambda: datetime.now(timezone.utc)
    )


@lru_cache(maxsize=1)
def get_line_delivery_task_admin_application() -> LineDeliveryTaskAdminApplication:
    return LineDeliveryTaskAdminApplication(open_line_unit_of_work)


@lru_cache(maxsize=1)
def get_line_rich_menu_application() -> LineRichMenuApplication:
    return LineRichMenuApplication(open_line_unit_of_work)


@lru_cache(maxsize=1)
def get_line_order_group_query_application() -> LineOrderGroupQueryApplication:
    return LineOrderGroupQueryApplication(open_line_unit_of_work)


@lru_cache(maxsize=1)
def get_line_feedback_application() -> LineFeedbackApplication:
    return LineFeedbackApplication(open_line_unit_of_work, lambda: datetime.now(timezone.utc))


@lru_cache(maxsize=1)
def get_line_runtime_application() -> LineRuntimeApplication:
    return LineRuntimeApplication(
        open_line_unit_of_work,
        lambda unit_of_work: MySqlLineRuntimeRepository(unit_of_work._connection),
    )


def get_line_database_health() -> LineDatabaseHealthView:
    connection = None
    try:
        connection = get_connection()
        repository = MySqlLineRuntimeRepository(connection)
        worker = classify_line_worker_health(
            repository.latest_heartbeat(),
            stale_after_seconds=float(os.getenv("LINE_WORKER_STALE_SECONDS", "90")),
        )
        return LineDatabaseHealthView(
            ok=repository.database_ready(),
            line_task_counts=LegacyLineTaskCountsView.model_validate(
                repository.legacy_task_counts()
            ),
            queue_counts=LineQueueCountsView.model_validate(repository.queue_counts()),
            worker=LineWorkerHealthView.model_validate(worker),
        )
    except Exception:
        return LineDatabaseHealthView(
            ok=False,
            line_task_counts=LegacyLineTaskCountsView(),
            queue_counts=LineQueueCountsView(),
            worker=LineWorkerHealthView(status="unknown", running=False),
            error_code="line_database_unavailable",
        )
    finally:
        if connection is not None:
            connection.close()


@lru_cache(maxsize=1)
def get_line_wakeup_publisher():
    return _wakeup_publisher()


def publish_line_wakeup_best_effort() -> None:
    try:
        get_line_wakeup_publisher().publish()
    except Exception as error:
        print(f"[LINE Runtime] Redis wake signal failed; DB fallback remains active: {error}")


def _wakeup_publisher():
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
    if redis_url:
        return RedisLineWakeupPublisher(redis_url)
    return NoopLineWakeupPublisher()


def record_line_webhook_security_receipt(
    request_fingerprint: str,
    signature_present: bool,
    outcome: LineWebhookVerificationOutcome,
    event_count: int,
    correlation_id: str,
) -> None:
    get_line_runtime_application().record_webhook_security_receipt(
        request_fingerprint,
        signature_present,
        outcome,
        event_count,
        correlation_id,
    )


__all__ = [
    "get_line_configuration_application",
    "get_line_notification_rule_administration",
    "get_line_notification_timeline_application",
    "get_line_notification_manual_replay_application",
    "get_line_delivery_task_admin_application",
    "get_line_rich_menu_application",
    "get_line_order_group_query_application",
    "get_line_runtime_application",
    "get_line_database_health",
    "get_line_webhook_intake",
    "get_line_wakeup_publisher",
    "line_webhook_runtime_mode",
    "publish_line_wakeup_best_effort",
    "record_line_webhook_security_receipt",
]

"""Composition root for canonical LINE webhook and independent worker adapters."""

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
from infrastructure.mysql.line_runtime_repository import MySqlLineRuntimeRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.line.runtime_contracts import (
    LineRuntimeMode,
    LineWebhookSecurityReceipt,
    LineWebhookVerificationOutcome,
)
from subsystems.line.runtime_cutover import validate_line_api_runtime
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.delivery_admin_application import (
    LineDeliveryTaskAdminApplication,
)
from subsystems.line.rich_menu_application import LineRichMenuApplication
from subsystems.line.order_group_application import LineOrderGroupQueryApplication
from subsystems.line.webhook_intake import LineWebhookIntake


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
def get_line_delivery_task_admin_application() -> LineDeliveryTaskAdminApplication:
    return LineDeliveryTaskAdminApplication(open_line_unit_of_work)


@lru_cache(maxsize=1)
def get_line_rich_menu_application() -> LineRichMenuApplication:
    return LineRichMenuApplication(open_line_unit_of_work)


@lru_cache(maxsize=1)
def get_line_order_group_query_application() -> LineOrderGroupQueryApplication:
    return LineOrderGroupQueryApplication(open_line_unit_of_work)


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
    receipt = LineWebhookSecurityReceipt(
        request_fingerprint,
        signature_present,
        outcome,
        event_count,
        correlation_id,
        datetime.now(timezone.utc),
    )
    connection = get_connection()
    try:
        connection.begin()
        MySqlLineRuntimeRepository(connection).append_security_receipt(receipt)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


__all__ = [
    "get_line_configuration_application",
    "get_line_delivery_task_admin_application",
    "get_line_rich_menu_application",
    "get_line_order_group_query_application",
    "get_line_webhook_intake",
    "get_line_wakeup_publisher",
    "line_webhook_runtime_mode",
    "publish_line_wakeup_best_effort",
    "record_line_webhook_security_receipt",
]

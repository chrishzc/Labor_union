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
from subsystems.line.webhook_intake import LineWebhookIntake


def line_webhook_runtime_mode() -> LineRuntimeMode:
    value = os.getenv("LINE_WEBHOOK_RUNTIME_MODE", "legacy").strip().lower()
    try:
        mode = LineRuntimeMode(value)
    except ValueError as error:
        raise RuntimeError("LINE_WEBHOOK_RUNTIME_MODE must be legacy or canonical") from error
    if mode is LineRuntimeMode.COMPATIBILITY:
        raise RuntimeError("compatibility mode is worker-only, not a webhook mode")
    return mode


@lru_cache(maxsize=1)
def get_line_webhook_intake() -> LineWebhookIntake:
    channel_secret = os.getenv("LINE_CHANNEL_SECRET", "").strip()
    publisher = _wakeup_publisher()
    return LineWebhookIntake(
        LineWebhookSignatureVerifier(channel_secret),
        open_line_unit_of_work,
        publisher,
    )


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
    "get_line_webhook_intake",
    "line_webhook_runtime_mode",
    "record_line_webhook_security_receipt",
]

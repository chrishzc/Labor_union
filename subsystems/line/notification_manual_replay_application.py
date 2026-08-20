"""
File: notification_manual_replay_application.py
Description: 讓管理員先預覽再以新 immutable source 執行 historical-silent LINE 通知手動重送。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort


class LineNotificationManualReplayApplication:
    def __init__(self, unit_of_work_factory: Callable[[], LineUnitOfWorkPort], now: Callable[[], datetime]) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def preview(self, source_event_id: int, actor: ActorContext) -> dict[str, object]:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.notification_rules.preview_manual_replay(source_event_id)

    def apply(self, source_event_id: int, actor: ActorContext, reason: str, idempotency_key: IdempotencyKey, correlation_id: CorrelationId) -> int:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        if not reason.strip():
            raise ValueError("manual replay reason is required")
        with self._unit_of_work_factory() as unit_of_work:
            replayed_source_id = unit_of_work.notification_rules.manual_replay_source(
                source_event_id, f"manual-replay:{source_event_id}:{idempotency_key.value}", self._now()
            )
            unit_of_work.audit.append(LineAuditIntent(
                "line.notification.manual_replay", actor.actor_id,
                "line_notification_source_event", str(source_event_id),
            ))
            unit_of_work.commit()
        return replayed_source_id


__all__ = ["LineNotificationManualReplayApplication"]

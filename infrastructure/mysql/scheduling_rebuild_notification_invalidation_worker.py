"""
File: scheduling_rebuild_notification_invalidation_worker.py
Description: 在單一 MySQL outer transaction 執行排班重建後的 LINE 舊提醒取消投影。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from infrastructure.mysql.scheduling_rebuild_notification_invalidation_repository import (
    MySqlSchedulingRebuildNotificationInvalidationRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.line.scheduling_rebuild_notification_invalidation import (
    SchedulingRebuildNotificationInvalidationError,
    SchedulingRebuildNotificationInvalidationProjector,
)


class MySqlSchedulingRebuildNotificationInvalidationWorker:
    # A committed rebuild invalidates old assignment-derived reminders before
    # any due LINE task may cross the provider boundary in the same cycle.
    run_before_delivery = True

    def __init__(
        self, connection_factory: Callable[[], object], now: Callable[[], datetime]
    ) -> None:
        self._connection_factory = connection_factory
        self._now = now

    def run_once(self) -> int:
        connection = self._connection_factory()
        try:
            with MySqlUnitOfWork(connection) as unit_of_work:
                try:
                    result = SchedulingRebuildNotificationInvalidationProjector(
                        MySqlSchedulingRebuildNotificationInvalidationRepository(connection),
                        MySqlLineNotificationRepository(connection),
                    ).run_once(self._now())
                except SchedulingRebuildNotificationInvalidationError:
                    # Persist the bounded retry/failed state recorded by the
                    # projector, then propagate so provider delivery is blocked.
                    unit_of_work.commit()
                    raise
                if result:
                    unit_of_work.commit()
                return result
        finally:
            connection.close()


__all__ = ["MySqlSchedulingRebuildNotificationInvalidationWorker"]

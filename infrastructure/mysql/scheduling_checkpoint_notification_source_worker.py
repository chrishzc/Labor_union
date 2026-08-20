"""
File: scheduling_checkpoint_notification_source_worker.py
Description: 在同一 MySQL transaction 將 Scheduling checkpoint outbox 登錄為 LINE notification source event。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from infrastructure.mysql.scheduling_checkpoint_notification_source_repository import (
    MySqlSchedulingCheckpointNotificationSourceRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.line.scheduling_checkpoint_notification_source import (
    SchedulingCheckpointNotificationSourceProjector,
)


class MySqlSchedulingCheckpointNotificationSourceWorker:
    def __init__(self, connection_factory: Callable[[], object], now: Callable[[], datetime]) -> None:
        self._connection_factory = connection_factory
        self._now = now

    def run_once(self) -> int:
        connection = self._connection_factory()
        try:
            with MySqlUnitOfWork(connection) as unit_of_work:
                result = SchedulingCheckpointNotificationSourceProjector(
                    MySqlSchedulingCheckpointNotificationSourceRepository(connection),
                    MySqlLineNotificationRepository(connection),
                ).run_once(self._now())
                if result:
                    unit_of_work.commit()
                return result
        finally:
            connection.close()


__all__ = ["MySqlSchedulingCheckpointNotificationSourceWorker"]

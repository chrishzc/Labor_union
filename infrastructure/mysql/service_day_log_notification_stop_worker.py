"""
File: service_day_log_notification_stop_worker.py
Description: 在單一 MySQL outer transaction 執行服務日日誌完成後的 LINE 提醒取消投影。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from infrastructure.mysql.service_day_log_notification_stop_repository import (
    MySqlServiceDayLogNotificationStopRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.line.service_day_log_notification_stop import (
    ServiceDayLogNotificationStopProjector,
)


class MySqlServiceDayLogNotificationStopWorker:
    def __init__(self, connection_factory: Callable[[], object], now: Callable[[], datetime]) -> None:
        self._connection_factory = connection_factory
        self._now = now

    def run_once(self) -> int:
        connection = self._connection_factory()
        try:
            with MySqlUnitOfWork(connection) as unit_of_work:
                result = ServiceDayLogNotificationStopProjector(
                    MySqlServiceDayLogNotificationStopRepository(connection),
                    MySqlLineNotificationRepository(connection),
                ).run_once(self._now())
                if result:
                    unit_of_work.commit()
                return result
        finally:
            connection.close()


__all__ = ["MySqlServiceDayLogNotificationStopWorker"]

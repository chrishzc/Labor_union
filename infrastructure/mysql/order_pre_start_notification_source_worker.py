"""
File: order_pre_start_notification_source_worker.py
Description: 在同一 MySQL transaction 將即將開始服務之案件登錄為 LINE notification source event 並派發通知決策。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from infrastructure.mysql.order_pre_start_notification_source_repository import (
    MySqlOrderPreStartNotificationSourceRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.line.order_pre_start_notification_source import (
    OrderPreStartNotificationSourceProjector,
)


class MySqlOrderPreStartNotificationSourceWorker:
    def __init__(self, connection_factory: Callable[[], object], now: Callable[[], datetime]) -> None:
        self._connection_factory = connection_factory
        self._now = now

    def run_once(self, *, target_date: date | None = None) -> int:
        connection = self._connection_factory()
        try:
            # Two worker processes may select the same still-unregistered source
            # before either reaches INSERT IGNORE.  READ COMMITTED keeps the
            # duplicate readback in this same transaction able to observe the
            # source row committed by the winner after the unique-key wait.
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            with MySqlUnitOfWork(connection) as unit_of_work:
                result = OrderPreStartNotificationSourceProjector(
                    MySqlOrderPreStartNotificationSourceRepository(connection),
                    MySqlLineNotificationRepository(connection),
                ).run_once(self._now(), target_date=target_date)
                if result:
                    unit_of_work.commit()
                return result
        finally:
            connection.close()


__all__ = ["MySqlOrderPreStartNotificationSourceWorker"]

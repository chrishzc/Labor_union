"""
File: service_day_checkpoint_worker.py
Description: 以 MySQL outer transaction 執行 Scheduling 每日服務時段 checkpoint 的 adapter composition。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from infrastructure.mysql.service_day_checkpoint_repository import MySqlServiceDayCheckpointRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.scheduling.service_day_checkpoint_workflow import ServiceDayCheckpointWorker


class MySqlServiceDayCheckpointWorker:
    def __init__(self, connection_factory: Callable[[], object], now: Callable[[], datetime]) -> None:
        self._connection_factory = connection_factory
        self._now = now

    def run_once(self) -> int:
        connection = self._connection_factory()
        try:
            with MySqlUnitOfWork(connection) as unit_of_work:
                return ServiceDayCheckpointWorker(
                    lambda: MySqlServiceDayCheckpointRepository(connection),
                    unit_of_work.commit,
                    self._now,
                ).run_once()
        finally:
            connection.close()


__all__ = ["MySqlServiceDayCheckpointWorker"]

"""
File: line_notification_anomaly_worker.py
Description: 從 immutable LINE 通知 decision 投影 LINE-006，使用異常中心既有 checkpoint 冪等重跑。
"""

from __future__ import annotations

from typing import Callable

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import AnomalyMySqlUnitOfWork, MySqlAnomalyRepository
from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from subsystems.anomalies.alert_workflow import AnomalyApplication
from subsystems.anomalies.line_notification_anomaly_projector import LineNotificationAnomalyProjector


class MySqlLineNotificationAnomalyWorker:
    def __init__(self, connection_factory: Callable[[], object]) -> None:
        self._connection_factory = connection_factory

    def run_once(self, *, limit: int = 100) -> int:
        source_connection = self._connection_factory()
        try:
            sources = MySqlLineNotificationRepository(source_connection).list_anomaly_sources(limit=limit)
        finally:
            source_connection.close()
        projected = 0
        for source in sources:
            connection = self._connection_factory()
            try:
                application = AnomalyApplication(default_anomaly_registry(), MySqlAnomalyRepository(connection), lambda: AnomalyMySqlUnitOfWork(connection))
                if LineNotificationAnomalyProjector(application).project(source):
                    projected += 1
            finally:
                connection.close()
        return projected


__all__ = ["MySqlLineNotificationAnomalyWorker"]

"""
File: line_notification_reconciliation_worker.py
Description: 以獨立 LINE transaction 補建遺失 notification decision，不重送既有 delivery task。
"""

from __future__ import annotations

from typing import Callable

from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from subsystems.line.notification_reconciliation import LineNotificationReconciler


class MySqlLineNotificationReconciliationWorker:
    def __init__(self, connection_factory: Callable[[], object]) -> None:
        self._connection_factory = connection_factory

    def run_once(self, *, limit: int = 100) -> int:
        connection = self._connection_factory()
        try:
            connection.begin()
            repository = MySqlLineNotificationRepository(connection)
            result = LineNotificationReconciler().reconcile(repository, limit=limit)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["MySqlLineNotificationReconciliationWorker"]

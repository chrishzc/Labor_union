"""
File: line_notification_reconciliation_worker.py
Description: 以獨立 LINE transaction 補建遺失 notification decision，不重送既有 delivery task。
"""

from __future__ import annotations

from typing import Callable

from subsystems.line.notification_reconciliation import LineNotificationReconciler


class MySqlLineNotificationReconciliationWorker:
    """Borrow a caller-owned notification repository for one bounded pass."""

    def __init__(self, repository_factory: Callable[[], object]) -> None:
        self._repository_factory = repository_factory

    def run_once(self, *, limit: int = 100) -> int:
        return LineNotificationReconciler().reconcile(
            self._repository_factory(), limit=limit
        )


__all__ = ["MySqlLineNotificationReconciliationWorker"]

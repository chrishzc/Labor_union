"""
File: notification_reconciliation.py
Description: 對已登錄但尚無 terminal decision 的 LINE 通知來源進行冪等補償，不直接重送 provider。
"""

from __future__ import annotations

from typing import Protocol

from subsystems.line.notification_policy import NotificationSourceEvent


class NotificationReconciliationRepositoryPort(Protocol):
    def list_sources_without_decisions(
        self, *, limit: int = 100
    ) -> tuple[NotificationSourceEvent, ...]: ...

    def register_and_project(self, event: NotificationSourceEvent) -> int: ...


class LineNotificationReconciler:
    """Replays only source-to-decision projection; intent uniqueness prevents provider resends."""

    def reconcile(self, repository: NotificationReconciliationRepositoryPort, *, limit: int = 100) -> int:
        reconciled = 0
        for event in repository.list_sources_without_decisions(limit=limit):
            repository.register_and_project(event)
            reconciled += 1
        return reconciled


__all__ = ["LineNotificationReconciler", "NotificationReconciliationRepositoryPort"]

"""
File: order_pre_start_notification_source.py
Description: 投影正式開工當天群組提醒與既有第二期款提醒；不直接發送。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.line.service_start_day import ServiceStartDayCandidate
from subsystems.line.second_payment_notifications import SecondPaymentNotification
from subsystems.line.service_completion_notifications import ServiceCompletionNotification

from subsystems.line.notification_policy import NotificationSourceEvent
from subsystems.line.notification_source_adapters import (
    from_order_service_start_day,
)


class OrderPreStartScannerPort(Protocol):
    def find_due_candidates(self, target_date: date) -> tuple[ServiceStartDayCandidate, ...]:
        """Read the formal start day, original group and effective day assignments."""
        ...

    def find_second_payment_due_candidates(self, target_date: date) -> tuple[SecondPaymentNotification, ...]:
        """Only required, unpaid second payments due today; missing group remains a staff todo."""
        ...

    def find_second_payment_settlement_candidates(self) -> tuple[SecondPaymentNotification, ...]:
        """Only explicitly marked, committed and still-valid second-stage settlements."""
        ...

    def find_service_completion_candidates(self) -> tuple[ServiceCompletionNotification, ...]: ...


class NotificationSourceRegistryPort(Protocol):
    def register_and_project(self, event: NotificationSourceEvent) -> int:
        """Register source event and project decisions and intents."""
        ...


class OrderPreStartNotificationSourceProjector:
    def __init__(
        self,
        scanner: OrderPreStartScannerPort,
        registry: NotificationSourceRegistryPort,
    ) -> None:
        self._scanner = scanner
        self._registry = registry

    def run_once(self, now: datetime, *, target_date: date | None = None) -> int:
        if now.tzinfo is None:
            raise ValueError('notification scan requires timezone-aware time')
        local_day = now.astimezone(TAIPEI_TIME_ZONE).date()
        effective_target = target_date or local_day
        processed = 0

        # 1. Start-day group notice. Never fall back to a customer private chat.
        candidates = self._scanner.find_due_candidates(effective_target)
        for candidate in candidates:
            event = from_order_service_start_day(candidate, occurred_at=now)
            self._registry.register_and_project(event)
            processed += 1

        # 2. Second payment reminder candidates (only for orders requiring second payment)
        find_second = getattr(self._scanner, "find_second_payment_due_candidates", None)
        if callable(find_second):
            second_candidates = find_second(effective_target)
            for sc in second_candidates:
                self._registry.register_and_project(sc.event(now))
                processed += 1

        find_settlements = getattr(self._scanner, 'find_second_payment_settlement_candidates', None)
        if callable(find_settlements):
            for settlement in find_settlements():
                self._registry.register_and_project(settlement.event(now))
                processed += 1

        find_completions = getattr(self._scanner, 'find_service_completion_candidates', None)
        if callable(find_completions):
            for completion in find_completions():
                self._registry.register_and_project(completion.event(now))
                processed += 1
        return processed


__all__ = [
    "NotificationSourceRegistryPort",
    "OrderPreStartNotificationSourceProjector",
    "OrderPreStartScannerPort",
]

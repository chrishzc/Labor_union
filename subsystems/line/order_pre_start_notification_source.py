"""
File: order_pre_start_notification_source.py
Description: 掃描服務開始前 3 天之有效案件，將其投影為 LINE immutable source event，並由 Notification Registry 派發決策。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from subsystems.line.notification_policy import NotificationSourceEvent
from subsystems.line.notification_source_adapters import (
    from_order_pre_start_checkpoint,
    from_order_second_payment_checkpoint,
)


_TAIPEI_TIMEZONE = timezone(timedelta(hours=8), "Asia/Taipei")


@dataclass(frozen=True, slots=True)
class OrderPreStartCandidate:
    case_no: str
    planned_start_date: str
    first_payment_amount: int
    already_settled: bool
    client_line_user_id: str | None = None
    first_payment_due_date: str | None = None
    payment_state: str = "outstanding"


@dataclass(frozen=True, slots=True)
class OrderSecondPaymentCandidate:
    case_no: str
    second_payment_due_date: str
    second_payment_amount: int
    already_settled: bool
    client_line_user_id: str | None = None
    service_start_date: str | None = None
    payment_state: str = "outstanding"


class OrderPreStartScannerPort(Protocol):
    def find_due_candidates(self, target_date: date) -> tuple[OrderPreStartCandidate, ...]:
        """Find active orders scheduled to start on target_date with their payment facts."""
        ...

    def find_second_payment_due_candidates(self, target_date: date) -> tuple[OrderSecondPaymentCandidate, ...]:
        """Find active orders with second payment due on target_date."""
        ...


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
        business_date = now.astimezone(_TAIPEI_TIMEZONE).date()
        effective_target = target_date or (business_date + timedelta(days=3))
        processed = 0

        # 1. First payment pre-start candidates
        candidates = self._scanner.find_due_candidates(effective_target)
        for candidate in candidates:
            event = from_order_pre_start_checkpoint(
                case_no=candidate.case_no,
                planned_start_date=candidate.planned_start_date,
                first_payment_amount=candidate.first_payment_amount,
                already_settled=candidate.already_settled,
                occurred_at=now,
                client_line_user_id=candidate.client_line_user_id,
                first_payment_due_date=candidate.first_payment_due_date,
                payment_state=candidate.payment_state,
            )
            self._registry.register_and_project(event)
            processed += 1

        # 2. Second payment reminder candidates (only for orders requiring second payment)
        find_second = getattr(self._scanner, "find_second_payment_due_candidates", None)
        if callable(find_second):
            second_candidates = find_second(effective_target)
            for sc in second_candidates:
                event = from_order_second_payment_checkpoint(
                    case_no=sc.case_no,
                    second_payment_due_date=sc.second_payment_due_date,
                    second_payment_amount=sc.second_payment_amount,
                    already_settled=sc.already_settled,
                    occurred_at=now,
                    client_line_user_id=sc.client_line_user_id,
                    service_start_date=sc.service_start_date,
                    payment_state=sc.payment_state,
                )
                self._registry.register_and_project(event)
                processed += 1

        return processed


__all__ = [
    "NotificationSourceRegistryPort",
    "OrderPreStartCandidate",
    "OrderPreStartNotificationSourceProjector",
    "OrderPreStartScannerPort",
    "OrderSecondPaymentCandidate",
]

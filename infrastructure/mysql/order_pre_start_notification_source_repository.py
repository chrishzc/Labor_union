"""
File: order_pre_start_notification_source_repository.py
Description: 查詢正式開工當天群組／班表／待付金額，另保留第二期款查詢。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from infrastructure.mysql.service_start_day_repository import MySqlServiceStartDayRepository
from subsystems.line.service_start_day import ServiceStartDayCandidate
from infrastructure.mysql.second_payment_notification_repository import MySqlSecondPaymentNotificationRepository
from infrastructure.mysql.service_completion_notification_repository import MySqlServiceCompletionNotificationRepository


class MySqlOrderPreStartNotificationSourceRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def find_due_candidates(self, target_date: date) -> tuple[ServiceStartDayCandidate, ...]:
        return MySqlServiceStartDayRepository(self._connection).find_due_candidates(target_date)

    def find_second_payment_due_candidates(self, target_date: date):
        return MySqlSecondPaymentNotificationRepository(self._connection).find_due_candidates(target_date)

    def find_second_payment_settlement_candidates(self):
        return MySqlSecondPaymentNotificationRepository(self._connection).find_settlement_candidates()

    def find_service_completion_candidates(self):
        return MySqlServiceCompletionNotificationRepository(self._connection).find_candidates()


__all__ = ["MySqlOrderPreStartNotificationSourceRepository"]

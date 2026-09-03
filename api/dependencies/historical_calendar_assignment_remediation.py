"""Compose assignment-only historical calendar remediation."""

from __future__ import annotations

from infrastructure.mysql.historical_calendar_assignment_remediation_repository import (
    MySqlHistoricalCalendarAssignmentRemediationRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.orders.historical_calendar_assignment_remediation import (
    HistoricalCalendarAssignmentRemediationApplication,
)


def get_historical_calendar_assignment_remediation_application():
    connection = get_connection()
    try:
        yield HistoricalCalendarAssignmentRemediationApplication(
            MySqlHistoricalCalendarAssignmentRemediationRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


__all__ = ["get_historical_calendar_assignment_remediation_application"]

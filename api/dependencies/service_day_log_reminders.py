"""One outer transaction for union log-reminder commands; no provider composition."""
from datetime import UTC, datetime

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.service_day_log_reminder_repository import MySqlServiceDayLogReminderRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.line.service_day_log_reminders import ServiceDayLogReminderApplication


def get_service_day_log_reminders():
    connection = get_connection()
    try:
        yield ServiceDayLogReminderApplication(MySqlServiceDayLogReminderRepository(connection),
                                               lambda: MySqlUnitOfWork(connection), lambda: datetime.now(UTC))
    finally:
        connection.close()

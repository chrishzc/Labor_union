"""Compose Service Day Log operations with one application-owned transaction."""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.service_day_log_repository import MySqlServiceDayLogRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.scheduling.service_day_log_workflow import ServiceDayLogApplication


def get_service_day_log_application():
    connection = get_connection()
    try:
        yield ServiceDayLogApplication(
            MySqlServiceDayLogRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()

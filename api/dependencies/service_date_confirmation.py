"""Per-request composition for service-date confirmation."""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.matching_schedule_confirmation_repository import (
    MySqlMatchingScheduleConfirmationRepository,
)
from infrastructure.mysql.service_date_confirmation_repository import MySqlServiceDateConfirmationRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.orders.service_date_confirmation_workflow import ServiceDateConfirmationWorkflow


def get_service_date_confirmation_workflow():
    connection = get_connection()
    try:
        yield ServiceDateConfirmationWorkflow(
            MySqlServiceDateConfirmationRepository(connection),
            lambda: MySqlUnitOfWork(connection),
            MySqlMatchingScheduleConfirmationRepository(connection),
        )
    finally:
        connection.close()

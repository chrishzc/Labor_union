"""Per-request composition for official service date correction."""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.official_service_date_correction_repository import (
    MySqlOfficialServiceDateCorrectionRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.orders.official_service_date_correction_workflow import (
    OfficialServiceDateCorrectionWorkflow,
)


def get_official_service_date_correction_workflow():
    connection = get_connection()
    try:
        yield OfficialServiceDateCorrectionWorkflow(
            MySqlOfficialServiceDateCorrectionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()

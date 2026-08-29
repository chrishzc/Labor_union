from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.scheduling.matching_schedule_confirmation import MatchingScheduleConfirmationWorkflow

def get_matching_schedule_confirmation_workflow():
    connection = get_connection()
    try:
        yield MatchingScheduleConfirmationWorkflow(
            MySqlMatchingScheduleConfirmationRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()

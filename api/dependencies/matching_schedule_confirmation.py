from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
from subsystems.scheduling.matching_schedule_confirmation import MatchingScheduleConfirmationWorkflow

def get_matching_schedule_confirmation_workflow():
    connection = get_connection()
    try:
        yield MatchingScheduleConfirmationWorkflow(MySqlMatchingScheduleConfirmationRepository(connection))
    finally:
        connection.close()

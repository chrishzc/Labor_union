"""Compose service-start coordination with the existing canonical owner writers."""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.order_actual_start_repository import MySqlOrderActualStartRepository
from infrastructure.mysql.service_date_confirmation_repository import MySqlServiceDateConfirmationRepository
from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
from infrastructure.mysql.leave_substitution_repository import MySqlLeaveSubstitutionRepository
from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository
from infrastructure.mysql.service_start_arrangement import MySqlServiceStartArrangement
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.actual_start_workflow import ActualStartWorkflow
from subsystems.orders.service_date_confirmation_workflow import ServiceDateConfirmationWorkflow
from subsystems.scheduling.service_start_workflow import ServiceStartWorkflow
from api.dependencies.assignment_plan import build_assignment_plan_application
from api.dependencies.leave_substitution import _build_leave_workflow


def build_service_start_application(connection):
    units = lambda: MySqlUnitOfWork(connection)
    repository = MySqlServiceStartRepository(connection)
    actual = ActualStartWorkflow(MySqlOrderActualStartRepository(connection), units, SystemBusinessClock())
    dates = ServiceDateConfirmationWorkflow(MySqlServiceDateConfirmationRepository(connection),units,
        MySqlMatchingScheduleConfirmationRepository(connection))
    arrangement = MySqlServiceStartArrangement(repository,actual,dates,
        build_assignment_plan_application(connection).workflow,
        _build_leave_workflow(connection,MySqlLeaveSubstitutionRepository(connection)))
    return ServiceStartWorkflow(repository,arrangement,units)


def get_service_start_application():
    connection=get_connection()
    try:
        yield build_service_start_application(connection)
    finally:
        connection.close()

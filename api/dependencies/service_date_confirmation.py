"""Per-request composition for service-date confirmation."""

from functools import partial

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.matching_schedule_confirmation_repository import (
    MySqlMatchingScheduleConfirmationRepository,
)
from infrastructure.mysql.service_date_confirmation_repository import MySqlServiceDateConfirmationRepository
from infrastructure.mysql.order_actual_start_repository import MySqlOrderActualStartRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.actual_start_workflow import ActualStartWorkflow
from infrastructure.mysql.service_start_arrangement import preview_office_schedule, save_office_schedule
from api.dependencies.assignment_plan import build_assignment_plan_application
from subsystems.orders.service_date_confirmation_workflow import ServiceDateConfirmationWorkflow
from subsystems.orders.historical_restart_arrangement import (
    HistoricalRestartArrangementWorkflow,
)


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


def get_historical_restart_arrangement_workflow():
    connection = get_connection()
    try:
        yield HistoricalRestartArrangementWorkflow(
            MySqlServiceDateConfirmationRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


def get_historical_restart_schedule_save():
    connection = get_connection()
    try:
        repository = MySqlServiceDateConfirmationRepository(connection)
        actual_start_repository = MySqlOrderActualStartRepository(connection)

        def unit_of_work():
            return MySqlUnitOfWork(connection)

        yield partial(
            HistoricalRestartArrangementWorkflow(repository, unit_of_work).save_schedule,
            date_workflow=ServiceDateConfirmationWorkflow(
                repository, unit_of_work, MySqlMatchingScheduleConfirmationRepository(connection),
            ),
            actual_start_workflow=ActualStartWorkflow(
                actual_start_repository, unit_of_work, SystemBusinessClock(),
            ),
            actual_start_repository=actual_start_repository,
        )
    finally:
        connection.close()


def get_office_schedule_save():
    connection = get_connection()
    try:
        yield partial(save_office_schedule, connection, build_assignment_plan_application)
    finally:
        connection.close()


def get_office_schedule_preview():
    connection = get_connection()
    try:
        yield partial(preview_office_schedule, connection)
    finally:
        connection.close()

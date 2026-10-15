"""Compose automatic scheduling from existing owner preview and durable command ports."""

from api.dependencies.assignment_plan import build_assignment_plan_application
from infrastructure.mysql.automatic_service_arrangement_repository import MySqlAutomaticServiceArrangementSource
from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.jobs.command_application import DurableJobCommandApplication
from subsystems.scheduling.automatic_service_arrangement import AutomaticServiceArrangement


def build_service_arrangement_automation(connection):
    assignments = build_assignment_plan_application(connection)
    return AutomaticServiceArrangement(MySqlAutomaticServiceArrangementSource(connection, assignments), assignments, DurableJobCommandApplication(BackgroundJobRepository(connection), connection))


def get_service_arrangement_automation():
    connection = get_connection()
    try:
        yield build_service_arrangement_automation(connection)
    finally:
        connection.close()

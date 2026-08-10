"""Per-request construction for canonical case architecture bootstrap."""

from infrastructure.mysql.case_architecture_bootstrap_repository import (
    MySqlCaseArchitectureBootstrapRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.bootstrap.case_architecture_status import (
    CaseArchitectureBootstrapStatusService,
)
from subsystems.bootstrap.case_architecture_workflow import (
    CaseArchitectureBootstrapWorkflow,
)


def get_case_architecture_bootstrap_workflow():
    connection = get_connection()
    repository = MySqlCaseArchitectureBootstrapRepository(connection)
    workflow = CaseArchitectureBootstrapWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
    )
    try:
        yield workflow
    finally:
        connection.close()


def get_case_architecture_bootstrap_status_service():
    connection = get_connection()
    service = CaseArchitectureBootstrapStatusService(connection)
    try:
        yield service
    finally:
        connection.close()


__all__ = [
    "get_case_architecture_bootstrap_status_service",
    "get_case_architecture_bootstrap_workflow",
]

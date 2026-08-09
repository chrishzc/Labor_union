"""Per-request construction for the Actual Start application workflow."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.actual_start_workflow import (
    ActualStartWorkflow,
    ActualStartWorkflowRepository,
)


@dataclass(slots=True)
class ActualStartApplication:
    repository: ActualStartWorkflowRepository
    workflow: ActualStartWorkflow

    def query(self, case_no: str):
        return self.repository.load_for_preview(case_no).shared_facts

    def preview(self, case_no, new_actual_start_date):
        return self.workflow.preview(case_no, new_actual_start_date)

    def apply(self, request):
        return self.workflow.apply(request)


def get_actual_start_application():
    from infrastructure.mysql.order_actual_start_repository import (
        MySqlOrderActualStartRepository,
    )

    connection = get_connection()
    repository = MySqlOrderActualStartRepository(connection)
    workflow = ActualStartWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        SystemBusinessClock(),
    )
    try:
        yield ActualStartApplication(repository, workflow)
    finally:
        connection.close()

"""Per-request construction for Orders contract completion."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionWorkflow,
    ContractCompletionWorkflowRepository,
)


@dataclass(slots=True)
class ContractCompletionApplication:
    repository: ContractCompletionWorkflowRepository
    workflow: ContractCompletionWorkflow

    def query(self, case_no: str):
        return self.workflow.query(case_no)

    def preview(self, case_no, intent):
        return self.workflow.preview(case_no, intent)

    def apply(self, request):
        return self.workflow.apply(request)


def get_contract_completion_application():
    from infrastructure.mysql.order_contract_completion_repository import (
        MySqlOrderContractCompletionRepository,
    )

    connection = get_connection()
    repository = MySqlOrderContractCompletionRepository(connection)
    workflow = ContractCompletionWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        SystemBusinessClock(),
    )
    try:
        yield ContractCompletionApplication(repository, workflow)
    finally:
        connection.close()


__all__ = [
    "ContractCompletionApplication",
    "get_contract_completion_application",
]

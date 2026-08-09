"""Per-request construction for canonical deposit reversal."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.client_deposit_reversal_repository import (
    ClientDepositReversalMySqlUnitOfWork,
    MySqlClientDepositReversalRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.client_finance.deposit_reversal_workflow import (
    DepositReversalApplyRequest,
    DepositReversalWorkflow,
)


@dataclass(slots=True)
class ClientDepositReversalApplication:
    repository: MySqlClientDepositReversalRepository
    workflow: DepositReversalWorkflow

    def preview(self, selection):
        return self.workflow.preview(selection)

    def apply(self, request: DepositReversalApplyRequest):
        self.repository.bind_apply_request(request)
        try:
            return self.workflow.apply(request)
        finally:
            self.repository.clear_apply_request()


def get_client_deposit_reversal_application():
    connection = get_connection()
    repository = MySqlClientDepositReversalRepository(connection)
    workflow = DepositReversalWorkflow(
        repository,
        lambda: ClientDepositReversalMySqlUnitOfWork(connection),
    )
    try:
        yield ClientDepositReversalApplication(repository, workflow)
    finally:
        connection.close()

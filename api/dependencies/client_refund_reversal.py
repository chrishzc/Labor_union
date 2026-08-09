"""Per-request construction for Client Refund and Client Reversal."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.client_refund_reversal_repository import (
    ClientRefundReversalMySqlUnitOfWork,
    MySqlClientRefundReversalRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalApplyRequest,
    ClientRefundReversalSelection,
    ClientRefundReversalWorkflow,
)


@dataclass(slots=True)
class ClientRefundReversalApplication:
    repository: MySqlClientRefundReversalRepository
    workflow: ClientRefundReversalWorkflow

    def query(self, case_no: str):
        return self.repository.query(case_no)

    def preview(self, selection: ClientRefundReversalSelection, correlation_id):
        return self.workflow.preview(selection, correlation_id)

    def apply(self, request: ClientRefundReversalApplyRequest):
        self.repository.bind_apply_request(request)
        try:
            return self.workflow.apply(request)
        finally:
            self.repository.clear_apply_request()


def get_client_refund_reversal_application():
    connection = get_connection()
    repository = MySqlClientRefundReversalRepository(connection)
    workflow = ClientRefundReversalWorkflow(
        repository,
        lambda: ClientRefundReversalMySqlUnitOfWork(connection),
    )
    try:
        yield ClientRefundReversalApplication(repository, workflow)
    finally:
        connection.close()


__all__ = [
    "ClientRefundReversalApplication",
    "get_client_refund_reversal_application",
]

"""Per-request construction for Client Receipt reconciliation."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.client_receipt_reconciliation_repository import (
    ClientReceiptMySqlUnitOfWork,
    MySqlClientReceiptReconciliationRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationWorkflow,
    ReconciliationSelection,
)


@dataclass(slots=True)
class ClientReceiptReconciliationApplication:
    repository: MySqlClientReceiptReconciliationRepository
    workflow: ClientReconciliationWorkflow

    def query(self, case_no: str):
        return self.repository.query(case_no)

    def preview(self, selection: ReconciliationSelection):
        return self.workflow.preview(selection)

    def apply(self, request: ClientReconciliationApplyRequest):
        self.repository.bind_apply_request(request)
        try:
            return self.workflow.apply(request)
        finally:
            self.repository.clear_apply_request()


def get_client_receipt_reconciliation_application():
    connection = get_connection()
    repository = MySqlClientReceiptReconciliationRepository(connection)
    workflow = ClientReconciliationWorkflow(
        repository,
        lambda: ClientReceiptMySqlUnitOfWork(connection),
    )
    try:
        yield ClientReceiptReconciliationApplication(repository, workflow)
    finally:
        connection.close()


__all__ = [
    "ClientReceiptReconciliationApplication",
    "get_client_receipt_reconciliation_application",
]

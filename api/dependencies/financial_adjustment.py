"""Per-request construction for cross-domain financial adjustments."""

from __future__ import annotations

from dataclasses import dataclass

from domains.client_finance.financial_adjustment import FinancialAdjustmentIntent
from infrastructure.mysql.financial_adjustment_repository import (
    FinancialAdjustmentMySqlUnitOfWork,
    MySqlFinancialAdjustmentRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.client_finance.financial_adjustment_workflow import (
    FinancialAdjustmentApplyRequest,
    FinancialAdjustmentWorkflow,
)


@dataclass(slots=True)
class FinancialAdjustmentApplication:
    repository: MySqlFinancialAdjustmentRepository
    workflow: FinancialAdjustmentWorkflow

    def query(self, case_no: str):
        return self.repository.query(case_no)

    def preview(self, intent: FinancialAdjustmentIntent, correlation_id):
        return self.workflow.preview(intent, correlation_id)

    def apply(self, request: FinancialAdjustmentApplyRequest):
        return self.workflow.apply(request)


def get_financial_adjustment_application():
    connection = get_connection()
    repository = MySqlFinancialAdjustmentRepository(connection)
    workflow = FinancialAdjustmentWorkflow(
        repository,
        lambda: FinancialAdjustmentMySqlUnitOfWork(connection),
    )
    try:
        yield FinancialAdjustmentApplication(repository, workflow)
    finally:
        connection.close()


__all__ = [
    "FinancialAdjustmentApplication",
    "get_financial_adjustment_application",
]

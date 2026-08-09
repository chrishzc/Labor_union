"""Per-request construction for Payroll query and adjustment workflows."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.payroll_adjustment_repository import (
    MySqlPayrollAdjustmentRepository,
    PayrollAdjustmentMySqlUnitOfWork,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.payroll.adjustment_workflow import (
    PayrollAdjustmentApplyRequest,
    PayrollAdjustmentWorkflow,
)


@dataclass(slots=True)
class PayrollApplication:
    repository: MySqlPayrollAdjustmentRepository
    workflow: PayrollAdjustmentWorkflow

    def query_case(self, case_no: str):
        return self.repository.query_case_payroll(case_no)

    def query_staff(self, staff_id: int):
        return self.repository.query_staff_obligations(staff_id)

    def preview(self, intent, correlation_id):
        return self.workflow.preview(intent, correlation_id)

    def apply(self, request: PayrollAdjustmentApplyRequest):
        return self.workflow.apply(request)


def get_payroll_application():
    connection = get_connection()
    repository = MySqlPayrollAdjustmentRepository(connection)
    workflow = PayrollAdjustmentWorkflow(
        repository,
        lambda: PayrollAdjustmentMySqlUnitOfWork(connection),
    )
    try:
        yield PayrollApplication(repository, workflow)
    finally:
        connection.close()


__all__ = ["PayrollApplication", "get_payroll_application"]

"""Per-request construction for standalone Payroll rebuild."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.payroll_rebuild_repository import (
    MySqlPayrollRebuildRepository,
    PayrollRebuildMySqlUnitOfWork,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.payroll.rebuild_workflow import (
    PayrollRebuildRequest,
    PayrollRebuildWorkflow,
)


@dataclass(slots=True)
class PayrollRebuildApplication:
    repository: MySqlPayrollRebuildRepository
    workflow: PayrollRebuildWorkflow

    def preview(self, case_no: str):
        return self.workflow.preview(case_no)

    def apply(self, request: PayrollRebuildRequest):
        return self.workflow.apply(request)

    def query_staff_month(self, staff_id: int, year: int, month: int):
        return self.repository.query_staff_month(staff_id, year, month)


def get_payroll_rebuild_application():
    connection = get_connection()
    try:
        yield build_payroll_rebuild_application(connection)
    finally:
        connection.close()


def build_payroll_rebuild_application(connection):
    repository = MySqlPayrollRebuildRepository(connection)
    workflow = PayrollRebuildWorkflow(
        repository,
        lambda: PayrollRebuildMySqlUnitOfWork(connection),
    )
    return PayrollRebuildApplication(repository, workflow)


__all__ = [
    "PayrollRebuildApplication",
    "build_payroll_rebuild_application",
    "get_payroll_rebuild_application",
]

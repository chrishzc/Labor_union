"""Per-request construction for the leave/substitution workflow."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.leave_substitution_impact_ports import (
    MySqlClientFinanceLeaveImpactPort,
    MySqlOrdersLeaveImpactPort,
    MySqlPayrollLeaveImpactPort,
)
from infrastructure.mysql.leave_substitution_repository import (
    MySqlLeaveSubstitutionRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.scheduling.leave_substitution_workflow import (
    LeaveSubstitutionWorkflow,
)


@dataclass(slots=True)
class LeaveSubstitutionApplication:
    connection: object
    workflow: LeaveSubstitutionWorkflow

    def preview(self, request):
        return self.workflow.preview(request)

    def apply(self, request):
        return self.workflow.apply(request)


def get_leave_substitution_application():
    connection = get_connection()
    workflow = LeaveSubstitutionWorkflow(
        MySqlLeaveSubstitutionRepository(connection),
        MySqlClientFinanceLeaveImpactPort(connection),
        MySqlPayrollLeaveImpactPort(connection),
        MySqlOrdersLeaveImpactPort(connection, SystemBusinessClock()),
        lambda: MySqlUnitOfWork(connection),
    )
    try:
        yield LeaveSubstitutionApplication(connection, workflow)
    finally:
        connection.close()

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
from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.scheduling.leave_substitution_workflow import (
    LeaveSubstitutionWorkflow,
)


@dataclass(slots=True)
class LeaveSubstitutionApplication:
    connection: object
    repository: MySqlLeaveSubstitutionRepository
    workflow: LeaveSubstitutionWorkflow

    def preview(self, request):
        return self.workflow.preview(request)

    def apply(self, request):
        return self.workflow.apply(request)

    def list_effective_assignments(self, case_no):
        return self.repository.list_effective_assignments(case_no)


def get_leave_substitution_application():
    connection = get_connection()
    repository = MySqlLeaveSubstitutionRepository(connection)
    workflow = LeaveSubstitutionWorkflow(
        repository,
        MySqlClientFinanceLeaveImpactPort(connection),
        MySqlPayrollLeaveImpactPort(connection),
        MySqlOrdersLeaveImpactPort(connection, SystemBusinessClock()),
        MySqlSchedulingHolidayQuery(connection),
        lambda: MySqlUnitOfWork(connection),
    )
    try:
        yield LeaveSubstitutionApplication(connection, repository, workflow)
    finally:
        connection.close()

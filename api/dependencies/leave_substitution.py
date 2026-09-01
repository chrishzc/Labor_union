"""File: leave_substitution.py
Description: 以單一MySQL connection組合請假代班workflow與outer UoW依賴。"""

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
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
)
from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
from infrastructure.mysql.staff_leave_intake_repository import (
    MySqlStaffLeaveIntakeRepository,
)
from infrastructure.mysql.substitution_payables_lineage_repository import (
    MySqlSubstitutionPayablesLineageRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.scheduling.leave_substitution_workflow import (
    LeaveSubstitutionWorkflow,
)
from subsystems.scheduling.leave_substitution_linked_request_resolution import (
    LeaveSubstitutionLinkedRequestResolution,
)
from subsystems.scheduling.substitution_payables_lineage import (
    SubstitutionPayablesLineageApplication,
)


@dataclass(slots=True)
class LeaveSubstitutionApplication:
    connection: object
    repository: MySqlLeaveSubstitutionRepository
    workflow: LeaveSubstitutionWorkflow
    payables_lineage: SubstitutionPayablesLineageApplication

    def preview(self, request):
        return self.workflow.preview(request)

    def apply(self, request):
        return self.workflow.apply(request)

    def list_effective_assignments(self, case_no):
        return self.repository.list_effective_assignments(case_no)

    def query_payables_lineage(self, case_no, batch_key):
        return self.payables_lineage.query(case_no, batch_key)


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
        LeaveSubstitutionLinkedRequestResolution(
            MySqlStaffLeaveIntakeRepository(connection),
            MySqlLineDeliveryTaskRepository(connection),
            SystemBusinessClock(),
        ),
    )
    try:
        yield LeaveSubstitutionApplication(
            connection,
            repository,
            workflow,
            SubstitutionPayablesLineageApplication(
                MySqlSubstitutionPayablesLineageRepository(connection)
            ),
        )
    finally:
        connection.close()

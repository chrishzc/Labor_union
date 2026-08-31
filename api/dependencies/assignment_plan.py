"""Per-request construction for the Assignment Plan workflow."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.assignment_plan_impact_ports import (
    MySqlClientFinanceAssignmentImpactPort,
    MySqlOrdersAssignmentImpactPort,
    MySqlPayrollAssignmentImpactPort,
)
from infrastructure.mysql.assignment_plan_repository import (
    MySqlAssignmentPlanRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.scheduling_anomaly_recheck_sink import MySqlSchedulingAnomalyRecheckSink
from shared_kernel.clock import SystemBusinessClock
from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanWorkflow


@dataclass(slots=True)
class AssignmentPlanApplication:
    connection: object
    workflow: AssignmentPlanWorkflow

    def query(self, case_no):
        return self.workflow.query(case_no)

    def preview(self, request):
        return self.workflow.preview(request)

    def apply(self, request):
        return self.workflow.apply(request)


def get_assignment_plan_application():
    connection = get_connection()
    application = build_assignment_plan_application(connection)
    try:
        yield application
    finally:
        connection.close()


def build_assignment_plan_application(connection):
    repository = MySqlAssignmentPlanRepository(connection)
    clock = SystemBusinessClock()
    workflow = AssignmentPlanWorkflow(
        repository,
        MySqlClientFinanceAssignmentImpactPort(connection),
        MySqlPayrollAssignmentImpactPort(connection),
        MySqlOrdersAssignmentImpactPort(connection, clock),
        lambda: MySqlUnitOfWork(connection),
        MySqlSchedulingAnomalyRecheckSink(connection),
    )
    return AssignmentPlanApplication(connection, workflow)

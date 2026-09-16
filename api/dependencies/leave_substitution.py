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
    LeaveSubstitutionPreviewRequest,
    LeaveSubstitutionWorkflow,
    LinkedLeaveRequestIntent,
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

    def preview_customer_defer(
        self, case_no, request_id, expected_version, assignment_id, correlation_id,
    ):
        intent = MySqlStaffLeaveIntakeRepository(self.connection).customer_defer_intent(
            request_id, expected_version, case_no, assignment_id,
        )
        workflow = _build_leave_workflow(
            self.connection, self.repository,
            customer_defer_case_no=case_no, customer_defer_intent=intent,
        )
        preview = workflow.preview(LeaveSubstitutionPreviewRequest(
            case_no, intent, correlation_id,
            LinkedLeaveRequestIntent(request_id, expected_version),
        ))
        return intent, preview

    def apply_customer_defer(self, request):
        if request.linked_request is None:
            raise ValueError("leave_request_identity_pair_required")
        # Do not rebuild the submitted intent or pre-read live consent here:
        # the canonical workflow must first replay an already committed batch.
        # Fresh commands revalidate consent/days in its linked-request lock hook.
        return _build_leave_workflow(
            self.connection, self.repository,
            customer_defer_case_no=request.case_no,
            customer_defer_intent=request.intent,
        ).apply(request)

    def list_effective_assignments(self, case_no):
        return self.repository.list_effective_assignments(case_no)

    def query_payables_lineage(self, case_no, batch_key):
        return self.payables_lineage.query(case_no, batch_key)


def _build_leave_workflow(
    connection, repository, *, customer_defer_case_no=None, customer_defer_intent=None,
):
    return LeaveSubstitutionWorkflow(
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
            customer_defer_case_no=customer_defer_case_no,
            customer_defer_intent=customer_defer_intent,
        ),
    )


def get_leave_substitution_application():
    connection = get_connection()
    repository = MySqlLeaveSubstitutionRepository(connection)
    workflow = _build_leave_workflow(connection, repository)
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

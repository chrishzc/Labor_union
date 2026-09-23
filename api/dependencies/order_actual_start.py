"""Per-request construction for the Actual Start application workflow."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.actual_start_workflow import (
    ActualStartApplyRequest,
    ActualStartDateOnlyApplyRequest,
    ActualStartWorkflow,
    ActualStartWorkflowError,
    ActualStartWorkflowRepository,
)


@dataclass(slots=True)
class ActualStartApplication:
    repository: ActualStartWorkflowRepository
    workflow: ActualStartWorkflow

    def query(self, case_no: str):
        return self.repository.load_actual_start_query(case_no, for_update=False)

    def preview(self, case_no, new_actual_start_date):
        query = self.repository.load_actual_start_query(case_no, for_update=False)
        if not query.has_formal_assignments:
            return self.workflow.preview_date_only(query, new_actual_start_date)
        return self.workflow.preview(case_no, new_actual_start_date)

    def apply(self, request: ActualStartApplyRequest | ActualStartDateOnlyApplyRequest):
        if isinstance(request, ActualStartDateOnlyApplyRequest):
            return self.workflow.apply_date_only(request)
        query = self.repository.load_actual_start_query(request.case_no, for_update=False)
        if not query.has_formal_assignments:
            raise ActualStartWorkflowError(TypedError(
                ErrorCategory.CONFLICT,
                "actual_start_mode_changed",
                "目前沒有正式指派，請重新預覽日期-only 操作。",
                request.correlation_id,
            ))
        return self.workflow.apply(request)


def get_actual_start_application():
    from infrastructure.mysql.order_actual_start_repository import (
        MySqlOrderActualStartRepository,
    )

    connection = get_connection()
    repository = MySqlOrderActualStartRepository(connection)
    workflow = ActualStartWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        SystemBusinessClock(),
    )
    try:
        yield ActualStartApplication(repository, workflow)
    finally:
        connection.close()

"""
File: historical_completion.py
Description: 建立每次請求專用的 HOB-E cross-owner completion query application。
"""

from __future__ import annotations

from infrastructure.mysql.historical_client_finance_completion_read_adapter import (
    MySqlClientFinanceCompletionReadAdapter,
)
from infrastructure.mysql.historical_orders_scheduling_completion_read_adapter import (
    MySqlHistoricalOrdersSchedulingCompletionReadAdapter,
)
from infrastructure.mysql.historical_staff_payables_completion_read_adapter import (
    MySqlStaffPayablesCompletionReadAdapter,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.historical_completion_writer import (
    MySqlHistoricalCompletionWriter,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.identities import CorrelationId
from subsystems.orders.historical_completion_projector import (
    HistoricalCompletionTerminalProjection,
    project_historical_completion,
)
from subsystems.orders.historical_completion_query import (
    HistoricalCompletionQueryRequest,
    HistoricalCompletionQueryWorkflow,
)
from subsystems.orders.historical_completion_apply import (
    ApplyHistoricalCompletion,
    HistoricalCompletionApplyWorkflow,
)


class HistoricalCompletionApplication:
    """Expose one cohesive fresh Query plus pure terminal projection."""

    def __init__(
        self,
        workflow: HistoricalCompletionQueryWorkflow,
        apply_workflow: HistoricalCompletionApplyWorkflow,
    ) -> None:
        self._workflow = workflow
        self._apply_workflow = apply_workflow

    def query(
        self, case_no: str, correlation_id: CorrelationId
    ) -> HistoricalCompletionTerminalProjection:
        result = self._workflow.query(
            HistoricalCompletionQueryRequest(case_no), correlation_id
        )
        return project_historical_completion(result)

    def preview(self, case_no: str):
        return self._apply_workflow.preview(case_no)

    def apply(self, request: ApplyHistoricalCompletion):
        return self._apply_workflow.apply(request)


def get_historical_completion_application():
    connection = get_connection()
    workflow = HistoricalCompletionQueryWorkflow(
        MySqlHistoricalOrdersSchedulingCompletionReadAdapter(connection),
        MySqlClientFinanceCompletionReadAdapter(connection),
        MySqlStaffPayablesCompletionReadAdapter(connection),
    )
    try:
        yield HistoricalCompletionApplication(
            workflow,
            HistoricalCompletionApplyWorkflow(
                MySqlHistoricalCompletionWriter(connection),
                lambda: MySqlUnitOfWork(connection),
                SystemBusinessClock(),
            ),
        )
    finally:
        connection.close()


__all__ = [
    "HistoricalCompletionApplication",
    "get_historical_completion_application",
]

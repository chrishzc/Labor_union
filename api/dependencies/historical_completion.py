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
from shared_kernel.identities import CorrelationId
from subsystems.orders.historical_completion_projector import (
    HistoricalCompletionTerminalProjection,
    project_historical_completion,
)
from subsystems.orders.historical_completion_query import (
    HistoricalCompletionQueryRequest,
    HistoricalCompletionQueryWorkflow,
)


class HistoricalCompletionApplication:
    """Expose one cohesive fresh Query plus pure terminal projection."""

    def __init__(self, workflow: HistoricalCompletionQueryWorkflow) -> None:
        self._workflow = workflow

    def query(
        self, case_no: str, correlation_id: CorrelationId
    ) -> HistoricalCompletionTerminalProjection:
        result = self._workflow.query(
            HistoricalCompletionQueryRequest(case_no), correlation_id
        )
        return project_historical_completion(result)


def get_historical_completion_application():
    connection = get_connection()
    workflow = HistoricalCompletionQueryWorkflow(
        MySqlHistoricalOrdersSchedulingCompletionReadAdapter(connection),
        MySqlClientFinanceCompletionReadAdapter(connection),
        MySqlStaffPayablesCompletionReadAdapter(connection),
    )
    try:
        yield HistoricalCompletionApplication(workflow)
    finally:
        connection.close()


__all__ = [
    "HistoricalCompletionApplication",
    "get_historical_completion_application",
]

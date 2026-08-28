"""
File: historical_operational_baseline.py
Description: 組裝每次請求專用的歷史 Orders 作業基準 application 與單一 outer UoW。
"""

from __future__ import annotations

from infrastructure.mysql.historical_operational_baseline_repository import (
    HistoricalOperationalBaselineMySqlUnitOfWork,
    MySqlHistoricalOperationalBaselineOutbox,
    MySqlHistoricalOperationalBaselineRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.orders.historical_operational_baseline_workflow import (
    HistoricalOperationalBaselineWorkflow,
)


class HistoricalOperationalBaselineApplication:
    def __init__(self, workflow: HistoricalOperationalBaselineWorkflow) -> None:
        self.workflow = workflow

    def query(self, identity, correlation_id):
        return self.workflow.query(identity, correlation_id)

    def preview(self, request, actor, correlation_id):
        return self.workflow.preview(request, actor, correlation_id)

    def apply(self, command):
        return self.workflow.apply(command)


def get_historical_operational_baseline_application():
    connection = get_connection()
    repository = MySqlHistoricalOperationalBaselineRepository(connection)
    outbox = MySqlHistoricalOperationalBaselineOutbox(connection)
    workflow = HistoricalOperationalBaselineWorkflow(
        repository,
        outbox,
        lambda: HistoricalOperationalBaselineMySqlUnitOfWork(connection),
    )
    try:
        yield HistoricalOperationalBaselineApplication(workflow)
    finally:
        connection.close()


__all__ = [
    "HistoricalOperationalBaselineApplication",
    "get_historical_operational_baseline_application",
]

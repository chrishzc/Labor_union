"""Per-request construction for controlled order reopening."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.reopen_workflow import OrderReopenWorkflow


@dataclass(slots=True)
class OrderReopenApplication:
    workflow: OrderReopenWorkflow

    def preview(self, case_no):
        return self.workflow.preview(case_no)

    def apply(self, request):
        return self.workflow.apply(request)


def get_order_reopen_application():
    from infrastructure.mysql.order_reopen_repository import (
        MySqlOrderReopenRepository,
    )

    connection = get_connection()
    repository = MySqlOrderReopenRepository(connection)
    workflow = OrderReopenWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        SystemBusinessClock(),
    )
    try:
        yield OrderReopenApplication(workflow)
    finally:
        connection.close()

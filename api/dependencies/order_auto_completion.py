"""Per-request construction for canonical Orders auto-completion."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.orders.auto_completion_workflow import AutoCompleteOrderService


@dataclass(slots=True)
class OrderAutoCompletionApplication:
    workflow: AutoCompleteOrderService

    def apply(self, request):
        return self.workflow.apply(request)


def get_order_auto_completion_application():
    from infrastructure.mysql.order_auto_completion_repository import MySqlOrderAutoCompletionRepository

    connection = get_connection()
    try:
        yield OrderAutoCompletionApplication(AutoCompleteOrderService(MySqlOrderAutoCompletionRepository(connection), lambda: MySqlUnitOfWork(connection)))
    finally:
        connection.close()

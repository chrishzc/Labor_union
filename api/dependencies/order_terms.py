"""Per-request construction for the Orders Terms application workflow."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.terms_workflow import OrderTermsWorkflow


@dataclass(slots=True)
class OrderTermsApplication:
    connection: object
    repository: MySqlOrderTermsRepository
    workflow: OrderTermsWorkflow

    def query(self, case_no: str):
        return self.repository.load_for_preview(case_no)

    def preview(self, case_no, proposed_terms):
        return self.workflow.preview(case_no, proposed_terms)

    def apply(self, request):
        return self.workflow.apply(request)


def get_order_terms_application():
    connection = get_connection()
    repository = MySqlOrderTermsRepository(connection)
    workflow = OrderTermsWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        SystemBusinessClock(),
    )
    try:
        yield OrderTermsApplication(connection, repository, workflow)
    finally:
        connection.close()

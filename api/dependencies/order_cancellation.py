"""Per-request construction for the Orders Cancellation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Protocol

from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.cancellation_workflow import (
    CancellationWorkflowFacts,
    CancellationWorkflowRepository,
    OrderCancellationWorkflow,
)


class OrderCancellationQueryRepository(
    CancellationWorkflowRepository,
    Protocol,
):
    def list_active_caregiver_options(
        self,
    ) -> tuple[Mapping[str, object], ...]: ...


@dataclass(slots=True)
class OrderCancellationApplication:
    repository: OrderCancellationQueryRepository
    workflow: OrderCancellationWorkflow

    def query(self, case_no: str):
        facts = self.repository.load_for_preview(case_no, ())
        options = self.repository.list_active_caregiver_options()
        return OrderCancellationQueryResult(facts, options)

    def preview(self, case_no, confirmed_service_days):
        return self.workflow.preview(case_no, confirmed_service_days)

    def apply(self, request):
        return self.workflow.apply(request)


@dataclass(frozen=True, slots=True)
class OrderCancellationQueryResult:
    facts: CancellationWorkflowFacts
    caregiver_options: tuple[Mapping[str, object], ...]


def get_order_cancellation_application():
    from infrastructure.mysql.order_cancellation_repository import (
        MySqlOrderCancellationRepository,
    )

    connection = get_connection()
    repository = MySqlOrderCancellationRepository(connection)
    workflow = OrderCancellationWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        SystemBusinessClock(),
    )
    try:
        yield OrderCancellationApplication(repository, workflow)
    finally:
        connection.close()

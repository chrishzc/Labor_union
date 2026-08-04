"""Per-request construction for the bounded Orders summary query."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.order_summary_query_repository import (
    MySqlOrderSummaryQueryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.orders.summary_query import (
    OrderSummaryQueryRequest,
    OrderSummaryQueryService,
)


@dataclass(slots=True)
class OrderSummaryApplication:
    service: OrderSummaryQueryService

    def query(self, request: OrderSummaryQueryRequest):
        return self.service.query(request)


def get_order_summary_application():
    connection = get_connection()
    try:
        yield OrderSummaryApplication(
            OrderSummaryQueryService(
                MySqlOrderSummaryQueryRepository(connection)
            )
        )
    finally:
        connection.close()


__all__ = [
    "OrderSummaryApplication",
    "get_order_summary_application",
]

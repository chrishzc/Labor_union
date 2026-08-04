"""Per-request construction for selected Orders calendar terms."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.order_calendar_detail_query_repository import (
    MySqlOrderCalendarDetailQueryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.orders.calendar_detail_query import (
    OrderCalendarDetailQueryService,
)


@dataclass(slots=True)
class OrderCalendarDetailApplication:
    service: OrderCalendarDetailQueryService

    def query(self, case_no: str):
        return self.service.query(case_no)


def get_order_calendar_detail_application():
    connection = get_connection()
    try:
        yield OrderCalendarDetailApplication(
            OrderCalendarDetailQueryService(
                MySqlOrderCalendarDetailQueryRepository(connection)
            )
        )
    finally:
        connection.close()


__all__ = [
    "OrderCalendarDetailApplication",
    "get_order_calendar_detail_application",
]

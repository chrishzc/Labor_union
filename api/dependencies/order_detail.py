"""Per-request construction for the typed selected-order detail query."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_detail_query_repository import MySqlOrderDetailQueryRepository
from subsystems.orders.detail_query import OrderDetailQueryService


class OrderDetailApplication:
    def __init__(self, service: OrderDetailQueryService) -> None:
        self._service = service

    def query(self, case_no: str):
        return self._service.query(case_no)


def get_order_detail_application():
    connection = get_connection()
    try:
        yield OrderDetailApplication(OrderDetailQueryService(MySqlOrderDetailQueryRepository(connection)))
    finally:
        connection.close()


__all__ = ["OrderDetailApplication", "get_order_detail_application"]

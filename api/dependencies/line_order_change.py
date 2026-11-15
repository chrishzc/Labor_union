"""Composition root for customer order-change LIFF intake."""

from functools import lru_cache

from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.customer_order_change_application import CustomerOrderChangeApplication
from subsystems.orders.order_change_requests import OrderChangeRequestsApplication


@lru_cache(maxsize=1)
def get_customer_order_change_application() -> CustomerOrderChangeApplication:
    return CustomerOrderChangeApplication(open_line_unit_of_work)


@lru_cache(maxsize=1)
def get_order_change_requests_application() -> OrderChangeRequestsApplication:
    return OrderChangeRequestsApplication(open_line_unit_of_work)

"""Composition root for customer order-change LIFF intake."""

from functools import lru_cache

from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.customer_order_change_application import CustomerOrderChangeApplication


@lru_cache(maxsize=1)
def get_customer_order_change_application() -> CustomerOrderChangeApplication:
    return CustomerOrderChangeApplication(open_line_unit_of_work)


__all__ = ["get_customer_order_change_application"]

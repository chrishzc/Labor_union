"""Per-request construction for typed order-information queries."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_information_repository import (
    MySqlOrderInformationRepository,
)
from subsystems.orders.order_information import OrderInformationQueryService


def get_order_information_application():
    connection = get_connection()
    try:
        yield OrderInformationQueryService(
            MySqlOrderInformationRepository(connection)
        )
    finally:
        connection.close()


__all__ = ["get_order_information_application"]

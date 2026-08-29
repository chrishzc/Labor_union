"""Per-request construction for the typed Orders lifecycle control query."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_lifecycle_control_query_repository import (
    MySqlOrderLifecycleControlQueryRepository,
)
from subsystems.orders.lifecycle_control_read_projection import (
    OrderLifecycleControlQueryService,
)


def get_order_lifecycle_control_application():
    connection = get_connection()
    try:
        yield OrderLifecycleControlQueryService(
            MySqlOrderLifecycleControlQueryRepository(connection)
        )
    finally:
        connection.close()


__all__ = ["get_order_lifecycle_control_application"]

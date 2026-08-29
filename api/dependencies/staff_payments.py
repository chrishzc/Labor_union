"""Request-scoped dependency for the Staff Payables compatibility query."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_payment_query_repository import (
    MySqlStaffPaymentQueryRepository,
)
from subsystems.staff_payables.legacy_payment_query import StaffPaymentQueryApplication


def get_staff_payment_query_application():
    connection = get_connection()
    try:
        yield StaffPaymentQueryApplication(MySqlStaffPaymentQueryRepository(connection))
    finally:
        connection.close()


__all__ = ["get_staff_payment_query_application"]

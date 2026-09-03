"""Compose the Orders intake terms bootstrap application."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_intake_terms_bootstrap_repository import (
    MySqlOrderIntakeTermsBootstrapRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.orders.order_intake_terms_bootstrap import (
    OrderIntakeTermsBootstrapApplication,
)


def get_order_intake_terms_bootstrap_application():
    connection = get_connection()
    try:
        yield OrderIntakeTermsBootstrapApplication(
            MySqlOrderIntakeTermsBootstrapRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


__all__ = ["get_order_intake_terms_bootstrap_application"]

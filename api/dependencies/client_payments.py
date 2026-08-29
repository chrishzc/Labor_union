"""Per-request composition for the authenticated Client Finance query."""

from __future__ import annotations

from infrastructure.mysql.client_payments_query_repository import (
    MySqlClientFinanceQueryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.client_finance.client_payments_query import (
    ClientFinanceQueryApplication,
)


def get_client_finance_query_application():
    connection = get_connection()
    repository = MySqlClientFinanceQueryRepository(connection)
    try:
        yield ClientFinanceQueryApplication(repository)
    finally:
        connection.close()


__all__ = [
    "ClientFinanceQueryApplication",
    "get_client_finance_query_application",
]

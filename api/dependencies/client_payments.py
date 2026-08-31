"""Per-request composition for the authenticated Client Finance query."""

from __future__ import annotations

from infrastructure.mysql.client_payments_query_repository import (
    MySqlClientFinanceQueryRepository,
)
from infrastructure.mysql.historical_client_payment_repository import (
    HistoricalClientPaymentMySqlUnitOfWork,
    MySqlHistoricalClientPaymentRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.client_finance.client_payments_query import (
    ClientFinanceQueryApplication,
)
from subsystems.client_finance.historical_payment_settlement import (
    HistoricalClientPaymentWorkflow,
)


def get_client_finance_query_application():
    connection = get_connection()
    repository = MySqlClientFinanceQueryRepository(connection)
    try:
        yield ClientFinanceQueryApplication(repository)
    finally:
        connection.close()


def get_historical_client_payment_workflow():
    connection = get_connection()
    repository = MySqlHistoricalClientPaymentRepository(connection)
    try:
        yield HistoricalClientPaymentWorkflow(
            repository,
            lambda: HistoricalClientPaymentMySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


__all__ = [
    "ClientFinanceQueryApplication",
    "get_client_finance_query_application",
    "get_historical_client_payment_workflow",
]

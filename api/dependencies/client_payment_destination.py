"""Per-request Client Finance payment-destination application."""

from infrastructure.mysql.client_payment_destination_repository import MySqlClientPaymentDestinationRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.client_finance.payment_destination_configuration import PaymentDestinationConfigurationApplication


def get_client_payment_destination_application():
    connection = get_connection()
    try:
        yield PaymentDestinationConfigurationApplication(
            MySqlClientPaymentDestinationRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


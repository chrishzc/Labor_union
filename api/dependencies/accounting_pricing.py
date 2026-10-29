"""One request connection, one outer pricing transaction."""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.client_finance.pricing_configuration import PricingConfigurationApplication


def get_pricing_application():
    connection = get_connection()
    try:
        yield PricingConfigurationApplication(MySqlPricingConfigurationRepository(connection), lambda: MySqlUnitOfWork(connection))
    finally:
        connection.close()

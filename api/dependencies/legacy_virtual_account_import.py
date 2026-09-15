"""Compose the Client Finance legacy virtual-account workbook service."""

from infrastructure.mysql.legacy_virtual_account_repository import MySqlLegacyVirtualAccountRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.client_finance.legacy_virtual_account_workbook import LegacyVirtualAccountWorkbookService


def get_legacy_virtual_account_workbook_service():
    connection = get_connection()
    try:
        yield LegacyVirtualAccountWorkbookService(
            MySqlLegacyVirtualAccountRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


__all__ = ["get_legacy_virtual_account_workbook_service"]

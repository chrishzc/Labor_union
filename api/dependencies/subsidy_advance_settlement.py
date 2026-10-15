"""Request-scoped composition for Client Finance advance settlement."""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.subsidy_advance_settlement_repository import MySqlAdvanceSettlementRepository
from subsystems.client_finance.subsidy_advance_settlement import AdvanceSettlementApplication


def get_advance_settlement_application():
    connection = get_connection()
    try:
        yield AdvanceSettlementApplication(MySqlAdvanceSettlementRepository(connection),
                                           lambda: MySqlUnitOfWork(connection))
    finally:
        connection.close()

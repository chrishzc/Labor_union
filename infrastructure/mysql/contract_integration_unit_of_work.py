"""Connection-owning MySQL Unit of Work for Contract Integration."""

from infrastructure.mysql.contract_integration_repository import MySqlContractIntegrationRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


class ContractIntegrationMySqlUnitOfWork(MySqlUnitOfWork):
    def __init__(self, connection) -> None:
        super().__init__(connection)
        self.contracts = MySqlContractIntegrationRepository(connection)


class ManagedContractIntegrationMySqlUnitOfWork(ContractIntegrationMySqlUnitOfWork):
    def __exit__(self, exception_type, exception, traceback) -> bool:
        try:
            return super().__exit__(exception_type, exception, traceback)
        finally:
            self._connection.close()


def open_contract_integration_unit_of_work():
    return ManagedContractIntegrationMySqlUnitOfWork(get_connection())


__all__ = ["ContractIntegrationMySqlUnitOfWork", "open_contract_integration_unit_of_work"]

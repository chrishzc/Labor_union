"""Per-request typed contract-context query construction."""

from infrastructure.mysql.contract_context_repository import MySqlContractContextRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.contract_integration.contract_context import ContractContextQueryService


def get_contract_context_service():
    connection = get_connection()
    try:
        yield ContractContextQueryService(MySqlContractContextRepository(connection))
    finally:
        connection.close()


__all__ = ["get_contract_context_service"]


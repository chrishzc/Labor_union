"""Per-request construction for the Government payer master workflow."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.government_subsidy.payer_master_workflow import GovernmentPayerMasterWorkflow


def get_government_payer_master_workflow():
    connection = get_connection()
    try:
        yield build_government_payer_master_workflow(connection)
    finally:
        connection.close()


def build_government_payer_master_workflow(connection):
    from infrastructure.mysql.government_payer_master_repository import MySqlGovernmentPayerMasterRepository

    return GovernmentPayerMasterWorkflow(
        MySqlGovernmentPayerMasterRepository(connection),
        lambda: MySqlUnitOfWork(connection),
    )

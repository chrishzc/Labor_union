"""
File: client_beclass_import.py
Description: 組合 Client BeClass temporary workbook application 與 MySQL adapter。
"""

from infrastructure.mysql.client_beclass_workbook_import_repository import ClientBeClassWorkbookImportRepository
from infrastructure.mysql.hcm_beclass_reconciliation_adapter import (
    MySqlHcmBeClassReconciliationAdapter,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.case_import.client_beclass_workbook_import import ClientBeClassWorkbookImportService


def get_client_beclass_workbook_import_service():
    connection = get_connection()
    try:
        yield ClientBeClassWorkbookImportService(
            ClientBeClassWorkbookImportRepository(connection),
            MySqlHcmBeClassReconciliationAdapter(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()

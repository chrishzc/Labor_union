"""
File: client_beclass_import.py
Description: 組合 Client BeClass temporary workbook application 與 MySQL adapter。
"""

from infrastructure.mysql.client_beclass_workbook_import_repository import ClientBeClassWorkbookImportRepository
from infrastructure.mysql.beclass_import_review_repository import MySqlBeClassImportReviewRepository
from infrastructure.mysql.hcm_beclass_reconciliation_adapter import (
    MySqlHcmBeClassReconciliationAdapter,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.case_import.client_beclass_workbook_import import ClientBeClassWorkbookImportService
from subsystems.case_import.beclass_review_intake import record_invalid_beclass_row


def get_client_beclass_workbook_import_service():
    connection = get_connection()
    try:
        yield ClientBeClassWorkbookImportService(
            ClientBeClassWorkbookImportRepository(connection),
            MySqlHcmBeClassReconciliationAdapter(connection),
            lambda: MySqlUnitOfWork(connection),
            review_recorder=lambda conn, **kwargs: record_invalid_beclass_row(conn, repository=MySqlBeClassImportReviewRepository(conn), **kwargs),
        )
    finally:
        connection.close()

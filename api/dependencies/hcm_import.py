"""
File: hcm_import.py
Description: 組合 HCM workbook coordinator 與暫時 legacy row intake adapter。
"""

from infrastructure.mysql.hcm_workbook_import_repository import HcmWorkbookImportRepository
from infrastructure.mysql.mysql_adapter import get_connection
from scripts.imports.import_client_hcm import HcmLegacyRowIntake
from subsystems.case_import.hcm_workbook_import import HcmWorkbookImportService


def get_hcm_workbook_import_service():
    connection = get_connection()
    try:
        yield HcmWorkbookImportService(
            HcmWorkbookImportRepository(connection),
            HcmLegacyRowIntake(connection),
        )
    finally:
        connection.close()

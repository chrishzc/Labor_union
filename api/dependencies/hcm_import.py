"""
File: hcm_import.py
Description: 組合 HCM workbook coordinator 與暫時 legacy row intake adapter。
"""

from infrastructure.mysql.hcm_workbook_import_repository import HcmWorkbookImportRepository
from infrastructure.mysql.hcm_resubmission_repository import MySqlHcmResubmissionRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from scripts.imports.import_client_hcm import HcmHistoricalRowIntake, HcmLegacyRowIntake, normalize_hcm_row
from subsystems.case_import.hcm_workbook_import import HcmWorkbookImportService
from subsystems.case_import.hcm_resubmission_workflow import HcmResubmissionWorkflow
from subsystems.case_import.hcm_resubmission_workbook import HcmResubmissionWorkbookService


def get_hcm_workbook_import_service():
    connection = get_connection()
    try:
        yield HcmWorkbookImportService(
            HcmWorkbookImportRepository(connection),
            HcmLegacyRowIntake(connection),
        )
    finally:
        connection.close()


def get_hcm_historical_workbook_import_service():
    connection = get_connection()
    try:
        yield HcmWorkbookImportService(
            HcmWorkbookImportRepository(connection),
            HcmHistoricalRowIntake(connection),
        )
    finally:
        connection.close()


def get_hcm_resubmission_workflow():
    connection = get_connection()
    try:
        yield HcmResubmissionWorkflow(
            MySqlHcmResubmissionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


def get_hcm_resubmission_workbook_service():
    connection = get_connection()
    try:
        repository = MySqlHcmResubmissionRepository(connection)
        workflow = HcmResubmissionWorkflow(repository, lambda: MySqlUnitOfWork(connection))
        yield HcmResubmissionWorkbookService(
            workflow,
            HcmLegacyRowIntake(connection),
            repository.load_holiday_dates,
            normalize_hcm_row,
        )
    finally:
        connection.close()

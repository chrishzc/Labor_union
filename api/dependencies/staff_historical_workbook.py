"""
File: staff_historical_workbook.py
Description: 組合 Staff 歷史 workbook typed application 與 MySQL adapters。
"""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.beclass_import_review_repository import MySqlBeClassImportReviewRepository
from infrastructure.mysql.staff_historical_workbook_repository import MySqlStaffHistoricalWorkbookRepository
from infrastructure.mysql.staff_historical_adoption_repository import MySqlStaffHistoricalAdoptionRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.case_import.staff_historical_workbook_adoption import StaffHistoricalWorkbookService
from subsystems.case_import.beclass_review_intake import record_invalid_beclass_row


def _record_staff_historical_review(connection, **kwargs):
    kwargs.pop("repository", None)
    return record_invalid_beclass_row(
        connection,
        repository=MySqlBeClassImportReviewRepository(connection),
        **kwargs,
    )


def get_staff_historical_workbook_service():
    connection = get_connection()
    try:
        yield StaffHistoricalWorkbookService(
            connection,
            MySqlStaffHistoricalWorkbookRepository(connection),
            lambda: MySqlUnitOfWork(connection),
            repository_factory=MySqlStaffHistoricalAdoptionRepository,
            review_recorder=_record_staff_historical_review,
        )
    finally:
        connection.close()

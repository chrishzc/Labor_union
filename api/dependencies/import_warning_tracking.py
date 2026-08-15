"""
File: import_warning_tracking.py
Description: 建立每請求獨立的匯入警示追蹤 application 與 MySQL 交易邊界。
"""

from infrastructure.mysql.import_warning_tracking_repository import MySqlImportWarningTrackingRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.anomalies.import_warning_tracking_workflow import ImportWarningTrackingApplication


def get_import_warning_tracking_application():
    connection = get_connection()
    application = ImportWarningTrackingApplication(
        MySqlImportWarningTrackingRepository(connection),
        lambda: MySqlUnitOfWork(connection),
    )
    try:
        yield application
    finally:
        connection.close()


__all__ = ["get_import_warning_tracking_application"]

"""
File: historical_order_adoption.py
Description: 組合 Orders historical workbook coordinator、repository 與單一 MySQL 交易邊界。
"""

from infrastructure.mysql.historical_order_adoption_repository import MySqlHistoricalOrderAdoptionRepository
from infrastructure.mysql.historical_order_workbook_import_repository import HistoricalOrderWorkbookImportRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.orders.historical_adoption_workflow import HistoricalOrderAdoptionWorkflow
from subsystems.orders.historical_order_workbook_import import HistoricalOrderWorkbookImportService
import pymysql
from fastapi import HTTPException, status


def get_historical_order_workbook_import_service():
    try:
        connection = get_connection()
    except pymysql.MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "historical_order_import_database_unavailable"},
        ) from error
    try:
        workflow = HistoricalOrderAdoptionWorkflow(
            MySqlHistoricalOrderAdoptionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        yield HistoricalOrderWorkbookImportService(
            HistoricalOrderWorkbookImportRepository(connection),
            workflow,
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()

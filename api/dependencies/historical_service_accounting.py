"""Composition root for historical service-day accounting."""

import pymysql
from fastapi import HTTPException, status

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.orders.historical_service_accounting_workflow import (
    HistoricalServiceAccountingWorkflow,
)
from datetime import datetime
from zoneinfo import ZoneInfo
from subsystems.orders.historical_precision_restart_workflow import HistoricalPrecisionRestartWorkflow


def get_historical_service_accounting_workflow():
    try:
        connection = get_connection()
    except pymysql.MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "historical_service_accounting_database_unavailable"},
        ) from error
    try:
        from infrastructure.mysql.historical_service_accounting_repository import (
            MySqlHistoricalServiceAccountingRepository,
        )

        yield HistoricalServiceAccountingWorkflow(
            MySqlHistoricalServiceAccountingRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


def get_historical_precision_restart_workflow():
    try:
        connection = get_connection()
    except pymysql.MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "historical_precision_restart_database_unavailable"},
        ) from error
    try:
        from infrastructure.mysql.historical_precision_restart_repository import MySqlHistoricalPrecisionRestartRepository

        yield HistoricalPrecisionRestartWorkflow(
            MySqlHistoricalPrecisionRestartRepository(connection),
            lambda: MySqlUnitOfWork(connection),
            lambda: datetime.now(ZoneInfo("Asia/Taipei")),
        )
    finally:
        connection.close()


__all__ = ["get_historical_service_accounting_workflow", "get_historical_precision_restart_workflow"]

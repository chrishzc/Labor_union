"""Composition root for historical service-day accounting."""

import pymysql
from fastapi import HTTPException, status

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.orders.historical_service_accounting_workflow import (
    HistoricalServiceAccountingWorkflow,
)


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


__all__ = ["get_historical_service_accounting_workflow"]

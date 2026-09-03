"""
File: historical_order_adoption.py
Description: 組合 Orders historical workbook coordinator、repository 與單一 MySQL 交易邊界。
"""

from infrastructure.mysql.admin_command_repository import AdminCommandRepository
from infrastructure.mysql.historical_order_adoption_cancellation_decorator import (
    MySqlHistoricalOrderAdoptionCancellationDecorator,
)
from infrastructure.mysql.historical_order_adoption_repository import (
    MySqlHistoricalOrderAdoptionRepository,
)
from infrastructure.mysql.historical_assignment_writer import MySqlHistoricalAssignmentWriter
from infrastructure.mysql.historical_pending_deposit_matching_repository import (
    MySqlHistoricalPendingDepositMatchingRepository,
)
from infrastructure.mysql.historical_actual_start_date_planner import (
    MySqlHistoricalActualStartDatePlanner,
)
from infrastructure.mysql.historical_order_workbook_import_repository import HistoricalOrderWorkbookImportRepository
from infrastructure.mysql.order_actual_start_repository import MySqlOrderActualStartRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.actual_start_workflow import ActualStartWorkflow
from subsystems.orders.historical_actual_start_rebuild import (
    HistoricalActualStartRebuilder,
)
from subsystems.orders.historical_adoption_workflow import HistoricalOrderAdoptionWorkflow
from subsystems.orders.historical_completed_assignment_repair import (
    HistoricalCompletedAssignmentRepairWorkflow,
)
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
            MySqlHistoricalOrderAdoptionCancellationDecorator(connection),
            lambda: MySqlUnitOfWork(connection),
            MySqlHistoricalAssignmentWriter(connection),
            HistoricalActualStartRebuilder(
                ActualStartWorkflow(
                    MySqlOrderActualStartRepository(connection),
                    lambda: MySqlUnitOfWork(connection),
                    SystemBusinessClock(),
                ),
                MySqlHistoricalActualStartDatePlanner(connection),
            ),
            matching_pending_deposit=MySqlHistoricalPendingDepositMatchingRepository(
                connection
            ),
        )
        yield HistoricalOrderWorkbookImportService(
            HistoricalOrderWorkbookImportRepository(connection),
            workflow,
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


def get_historical_completed_assignment_repair_workflow():
    try:
        connection = get_connection()
    except pymysql.MySQLError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "historical_assignment_repair_database_unavailable"},
        ) from error
    try:
        yield HistoricalCompletedAssignmentRepairWorkflow(
            MySqlHistoricalOrderAdoptionRepository(connection),
            AdminCommandRepository(connection),
            lambda: MySqlUnitOfWork(connection),
            MySqlHistoricalAssignmentWriter(connection),
        )
    finally:
        connection.close()

"""Compose Service Day Log operations with one application-owned transaction."""

from __future__ import annotations

import os

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.mysql.service_day_log_repository import MySqlServiceDayLogRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from subsystems.controlled_files.workflow import ControlledFileWorkflow
from subsystems.scheduling.service_day_log_workflow import ServiceDayLogApplication


def get_service_day_log_application():
    connection = get_connection()
    try:
        controlled_file_workflow = ControlledFileWorkflow(
            MySqlControlledFileWorkflowRepository(connection),
            FileSystemControlledFileStorage(
                os.getenv("CONTROLLED_FILE_STORAGE_ROOT", "").strip() or None
            ),
            lambda: MySqlUnitOfWork(connection),
            SystemBusinessClock(),
        )
        yield ServiceDayLogApplication(
            MySqlServiceDayLogRepository(connection),
            lambda: MySqlUnitOfWork(connection),
            controlled_file_workflow,
        )
    finally:
        connection.close()

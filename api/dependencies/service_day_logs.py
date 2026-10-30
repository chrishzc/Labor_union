"""Compose Service Day Log operations with one application-owned transaction."""

from __future__ import annotations


from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.file.storage_layout import configured_storage_root
from infrastructure.runtime.file_transfer_settings import file_read_capacity
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
                configured_storage_root(),
                max_staging_bytes=file_read_capacity(),
                max_read_bytes=file_read_capacity(),
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

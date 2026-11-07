"""
File: controlled_files.py
Description: 建立每次請求專用的 controlled-file workflow、MySQL UoW 與受控儲存 adapter。
"""

from __future__ import annotations

from collections.abc import Iterator

from infrastructure.db.controlled_file_repository import (
    MySqlControlledFileWorkflowRepository,
)
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.file.storage_layout import configured_storage_root
from infrastructure.runtime.file_transfer_settings import file_read_capacity
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from subsystems.controlled_files.workflow import ControlledFileWorkflow
from subsystems.controlled_files.maintenance import ControlledFileMaintenanceApplication


def build_controlled_file_workflow(connection) -> ControlledFileWorkflow:
    """Build on a caller-owned connection; this function never closes or commits it."""
    capacity = file_read_capacity()
    return ControlledFileWorkflow(
        MySqlControlledFileWorkflowRepository(connection),
        FileSystemControlledFileStorage(configured_storage_root(), max_staging_bytes=capacity, max_read_bytes=capacity),
        lambda: MySqlUnitOfWork(connection), SystemBusinessClock(),
    )


def get_controlled_file_workflow() -> Iterator[ControlledFileWorkflow]:
    connection = get_connection()
    try:
        yield build_controlled_file_workflow(connection)
    finally:
        connection.close()


def get_controlled_file_maintenance():
    connection = get_connection()
    try:
        capacity = file_read_capacity()
        yield ControlledFileMaintenanceApplication(
            MySqlControlledFileWorkflowRepository(connection),
            FileSystemControlledFileStorage(configured_storage_root(), max_staging_bytes=capacity, max_read_bytes=capacity),
            lambda: MySqlUnitOfWork(connection), SystemBusinessClock(),
        )
    finally:
        connection.close()


__all__ = ["get_controlled_file_workflow", "get_controlled_file_maintenance", "build_controlled_file_workflow"]

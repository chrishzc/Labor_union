"""
File: controlled_files.py
Description: 建立每次請求專用的 controlled-file workflow、MySQL UoW 與受控儲存 adapter。
"""

from __future__ import annotations

import os

from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from subsystems.controlled_files.workflow import ControlledFileWorkflow


def get_controlled_file_workflow():
    connection = get_connection()
    try:
        root = os.getenv("CONTROLLED_FILE_STORAGE_ROOT", "").strip() or None
        yield ControlledFileWorkflow(
            MySqlControlledFileWorkflowRepository(connection),
            FileSystemControlledFileStorage(root),
            lambda: MySqlUnitOfWork(connection),
            SystemBusinessClock(),
        )
    finally:
        connection.close()


__all__ = ["get_controlled_file_workflow"]

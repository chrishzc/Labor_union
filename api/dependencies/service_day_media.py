"""Compose LIFF service-day media staging outside the HTTP route."""

from __future__ import annotations

import os

from api.dependencies.line_worker_operation import _media_storage_root
from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.line.media_adapters import FileSystemLineMediaObjectStore
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.clock import SystemBusinessClock
from subsystems.line.liff_media_upload import LiffMealPhotoUploadApplication
from subsystems.controlled_files.workflow import ControlledFileWorkflow


def get_liff_meal_photo_upload_application() -> LiffMealPhotoUploadApplication:
    return LiffMealPhotoUploadApplication(
        open_line_unit_of_work,
        FileSystemLineMediaObjectStore(_media_storage_root()),
    )


def get_controlled_file_workflow():
    connection = get_connection()
    try:
        yield ControlledFileWorkflow(
            MySqlControlledFileWorkflowRepository(connection),
            FileSystemControlledFileStorage(
                os.getenv("CONTROLLED_FILE_STORAGE_ROOT", "").strip() or None
            ),
            lambda: MySqlUnitOfWork(connection),
            SystemBusinessClock(),
        )
    finally:
        connection.close()

from collections.abc import Iterator
from contextlib import contextmanager

from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.file.storage_layout import configured_storage_root
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_web_profile_repository import MySqlStaffWebProfileRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.runtime.file_transfer_settings import file_read_capacity
from shared_kernel.clock import SystemBusinessClock
from subsystems.controlled_files.workflow import ControlledFileWorkflow
from subsystems.staff.web_profile import StaffWebProfile


def build_staff_web_profile(connection) -> StaffWebProfile:
    def files() -> ControlledFileWorkflow:
        capacity = file_read_capacity()
        storage = FileSystemControlledFileStorage(
            configured_storage_root(), max_staging_bytes=capacity, max_read_bytes=capacity,
        )
        return ControlledFileWorkflow(
            MySqlControlledFileWorkflowRepository(connection), storage,
            lambda: MySqlUnitOfWork(connection), SystemBusinessClock(),
        )

    def registration_uow() -> MySqlUnitOfWork:
        # Missing file rows can share an index gap across different staff.
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        return MySqlUnitOfWork(connection)

    return StaffWebProfile(
        MySqlStaffWebProfileRepository(connection), files, lambda: MySqlUnitOfWork(connection),
        registration_uow=registration_uow,
    )


@contextmanager
def staff_web_profile_application() -> Iterator[StaffWebProfile]:
    connection = get_connection()
    try:
        yield build_staff_web_profile(connection)
    finally:
        connection.close()

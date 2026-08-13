"""Per-request construction for staff matching preference workflows."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_matching_preference_repository import (
    MySqlStaffMatchingPreferenceRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.scheduling.staff_matching_preference_workflow import (
    StaffMatchingPreferenceWorkflow,
)


@dataclass(slots=True)
class StaffMatchingPreferenceApplication:
    connection: object
    workflow: StaffMatchingPreferenceWorkflow


def get_staff_matching_preference_application():
    connection = get_connection()
    repository = MySqlStaffMatchingPreferenceRepository(connection)
    workflow = StaffMatchingPreferenceWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
    )
    try:
        yield StaffMatchingPreferenceApplication(connection, workflow)
    finally:
        connection.close()

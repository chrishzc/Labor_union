"""Request-scoped construction for Staff case-preference Preview -> Apply."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_case_preference_summary_command_repository import (
    MySqlStaffCasePreferenceCommandRepository,
)
from subsystems.staff.case_preference_summary_command import (
    StaffCasePreferenceCommandApplication,
)


def get_staff_case_preference_command_application():
    connection = get_connection()
    try:
        yield StaffCasePreferenceCommandApplication(
            MySqlStaffCasePreferenceCommandRepository(connection)
        )
    finally:
        connection.close()


__all__ = ["get_staff_case_preference_command_application"]

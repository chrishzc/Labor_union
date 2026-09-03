"""Request-scoped construction for the Staff case-preference summary query."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_case_preference_summary_query_repository import (
    MySqlStaffCasePreferenceSummaryQueryRepository,
)
from subsystems.staff.case_preference_summary_query import (
    StaffCasePreferenceSummaryQueryApplication,
    StaffCasePreferenceSummaryQueryService,
)


def get_staff_case_preference_summary_application():
    connection = get_connection()
    try:
        yield StaffCasePreferenceSummaryQueryApplication(
            StaffCasePreferenceSummaryQueryService(
                MySqlStaffCasePreferenceSummaryQueryRepository(connection)
            )
        )
    finally:
        connection.close()


__all__ = ["get_staff_case_preference_summary_application"]

"""Request-scoped construction for the bounded Staff summary query."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_summary_query_repository import (
    MySqlStaffSummaryQueryRepository,
)
from subsystems.staff.summary_query import (
    StaffSummaryQueryApplication,
    StaffSummaryQueryService,
)


def get_staff_summary_application():
    connection = get_connection()
    try:
        yield StaffSummaryQueryApplication(
            StaffSummaryQueryService(MySqlStaffSummaryQueryRepository(connection))
        )
    finally:
        connection.close()


__all__ = ["get_staff_summary_application"]

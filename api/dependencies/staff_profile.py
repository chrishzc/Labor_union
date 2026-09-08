"""Request-scoped construction for the Staff profile query."""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_profile_query_repository import (
    MySqlStaffProfileQueryRepository,
)
from subsystems.staff.profile_query import StaffProfileQueryApplication


def get_staff_profile_application():
    connection = get_connection()
    try:
        yield StaffProfileQueryApplication(MySqlStaffProfileQueryRepository(connection))
    finally:
        connection.close()


__all__ = ["get_staff_profile_application"]

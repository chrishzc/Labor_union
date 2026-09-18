"""Compose Staff Leave Intake with an application-owned MySQL transaction."""

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.scheduling.staff_leave_intake_workflow import StaffLeaveIntakeApplication


def get_staff_leave_intake_application():
    connection = get_connection()
    try:
        yield StaffLeaveIntakeApplication(
            MySqlStaffLeaveIntakeRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


def get_staff_leave_customer_coordination_application():
    """Compose the admin review with the same LINE-owned outer transaction."""
    from datetime import datetime, timezone

    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
    from subsystems.line.staff_leave_customer_coordination import (
        StaffLeaveCustomerCoordinationApplication,
    )

    return StaffLeaveCustomerCoordinationApplication(
        get_connection,
        open_line_unit_of_work,
        lambda: datetime.now(timezone.utc),
    )

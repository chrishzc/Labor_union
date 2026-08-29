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

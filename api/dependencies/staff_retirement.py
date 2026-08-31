"""
File: staff_retirement.py
Description: 建立 Staff lifecycle API 所需的 MySQL workflow。
"""

from dataclasses import dataclass
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_retirement_repository import MySqlStaffRetirementRepository
from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from subsystems.line.staff_retirement_effect import LineStaffRetirementEffect
from subsystems.staff.retirement_workflow import StaffLifecycleWorkflow


@dataclass(slots=True)
class StaffRetirementApplication:
    connection: object
    workflow: StaffLifecycleWorkflow


def get_staff_retirement_application():
    connection = get_connection()
    application = StaffRetirementApplication(
        connection,
        StaffLifecycleWorkflow(
            MySqlStaffRetirementRepository(connection),
            lambda: LineMySqlUnitOfWork(connection),
            SystemBusinessClock(),
            LineStaffRetirementEffect(),
        ),
    )
    try:
        yield application
    finally:
        connection.close()

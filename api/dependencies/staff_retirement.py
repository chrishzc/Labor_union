"""
File: staff_retirement.py
Description: 建立 Staff lifecycle API 所需的 MySQL workflow。
"""

from dataclasses import dataclass
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_retirement_repository import MySqlStaffRetirementRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from subsystems.staff.retirement_workflow import StaffLifecycleWorkflow


@dataclass(slots=True)
class StaffRetirementApplication:
    connection: object
    workflow: StaffLifecycleWorkflow


def get_staff_retirement_application():
    connection = get_connection()
    application = StaffRetirementApplication(connection, StaffLifecycleWorkflow(MySqlStaffRetirementRepository(connection), lambda: MySqlUnitOfWork(connection), SystemBusinessClock()))
    try:
        yield application
    finally:
        connection.close()

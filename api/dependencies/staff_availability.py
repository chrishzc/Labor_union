"""
File: staff_availability.py
Description: 建立 Staff Availability 的 MySQL repository 與唯一 outer UoW。
"""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from subsystems.scheduling.staff_availability_workflow import (
    StaffAvailabilityApplyRequest,
    StaffAvailabilityPreviewRequest,
    StaffAvailabilityQuery,
    StaffAvailabilityWorkflow,
)


@dataclass(slots=True)
class StaffAvailabilityApplication:
    workflow: StaffAvailabilityWorkflow

    def query(self, request: StaffAvailabilityQuery):
        return self.workflow.query(request)

    def preview(self, request: StaffAvailabilityPreviewRequest):
        return self.workflow.preview(request)

    def apply(self, request: StaffAvailabilityApplyRequest):
        return self.workflow.apply(request)


def get_staff_availability_application():
    from infrastructure.mysql.staff_availability_repository import (
        MySqlStaffAvailabilityRepository,
    )

    connection = get_connection()
    workflow = StaffAvailabilityWorkflow(
        MySqlStaffAvailabilityRepository(connection),
        SystemBusinessClock(),
        lambda: MySqlUnitOfWork(connection),
    )
    try:
        yield StaffAvailabilityApplication(workflow)
    finally:
        connection.close()


__all__ = [
    "StaffAvailabilityApplication",
    "get_staff_availability_application",
]

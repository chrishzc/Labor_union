"""Per-request construction for Staff Availability Preview/Apply."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.mysql_adapter import get_connection
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
    )
    try:
        yield StaffAvailabilityApplication(workflow)
    finally:
        connection.close()


__all__ = [
    "StaffAvailabilityApplication",
    "get_staff_availability_application",
]

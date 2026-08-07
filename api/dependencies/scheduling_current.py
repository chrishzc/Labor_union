"""Per-request construction for the current Scheduling projection."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.scheduling.current_projection_workflow import (
    SchedulingCurrentProjectionWorkflow,
    SchedulingCurrentQuery,
)


@dataclass(slots=True)
class SchedulingCurrentApplication:
    workflow: SchedulingCurrentProjectionWorkflow

    def query(self, request: SchedulingCurrentQuery):
        return self.workflow.query(request)


def get_scheduling_current_application():
    from infrastructure.mysql.scheduling_current_projection_repository import (
        MySqlSchedulingCurrentProjectionRepository,
    )

    connection = get_connection()
    workflow = SchedulingCurrentProjectionWorkflow(
        MySqlSchedulingCurrentProjectionRepository(connection),
        SystemBusinessClock(),
    )
    try:
        yield SchedulingCurrentApplication(workflow)
    finally:
        connection.close()


__all__ = [
    "SchedulingCurrentApplication",
    "get_scheduling_current_application",
]

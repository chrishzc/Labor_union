"""Request-scoped construction for the Scheduling multi-caregiver query."""

from __future__ import annotations

from infrastructure.mysql.multi_caregiver_schedule_query_repository import (
    MySqlMultiCaregiverScheduleQueryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.scheduling.multi_caregiver_schedule_query import (
    MultiCaregiverScheduleQueryApplication,
)


def get_multi_caregiver_schedule_query_application():
    connection = get_connection()
    try:
        yield MultiCaregiverScheduleQueryApplication(
            MySqlMultiCaregiverScheduleQueryRepository(connection)
        )
    finally:
        connection.close()


__all__ = ["get_multi_caregiver_schedule_query_application"]

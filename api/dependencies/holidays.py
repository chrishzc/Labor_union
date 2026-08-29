"""Compose Holiday maintenance with one application-owned MySQL transaction."""

from __future__ import annotations

import logging

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.scheduling.holiday_maintenance import HolidayMaintenanceApplication
from subsystems.scheduling.holiday_query_cache import invalidate_holiday_query_cache


LOGGER = logging.getLogger("labor_union.api.holidays")


def get_holiday_maintenance_application():
    connection = get_connection()
    try:
        yield HolidayMaintenanceApplication(
            MySqlSchedulingHolidayQuery(connection),
            lambda: MySqlUnitOfWork(connection),
            _invalidate_cache_after_commit,
        )
    finally:
        connection.close()


def _invalidate_cache_after_commit() -> None:
    try:
        invalidate_holiday_query_cache()
    except Exception:
        LOGGER.exception("Holiday cache invalidation failed after committed apply")

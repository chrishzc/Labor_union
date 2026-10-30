"""
File: holidays.py
Description: 組合國定假日維護交易邊界，並註冊選用 Redis 唯讀快取後端與提交後失效。
"""

from __future__ import annotations

import logging

from infrastructure.cache import default_redis_cache_backend
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.scheduling.holiday_maintenance import HolidayMaintenanceApplication
from subsystems.scheduling.holiday_query_cache import (
    configure_holiday_query_cache_backend,
    invalidate_holiday_query_cache,
)


LOGGER = logging.getLogger("labor_union.api.holidays")
configure_holiday_query_cache_backend(default_redis_cache_backend)


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

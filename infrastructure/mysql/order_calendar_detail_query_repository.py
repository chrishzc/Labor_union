"""MySQL adapter for selected Orders calendar terms."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_ORDER_CALENDAR_DETAIL_SQL = """
SELECT o.case_no,
       c.service_type AS service_mode
  FROM orders o
  JOIN clients c ON c.id = o.client_id
 WHERE o.case_no = %s
 LIMIT 1
"""


class MySqlOrderCalendarDetailQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_by_case_no(
        self,
        case_no: str,
    ) -> Mapping[str, object] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_CALENDAR_DETAIL_SQL, (case_no,))
            return cursor.fetchone()


__all__ = ["MySqlOrderCalendarDetailQueryRepository"]

"""MySQL adapter for the intentional one-order detail projection."""

from __future__ import annotations

from typing import Any


_ORDER_DETAIL_SQL = """
SELECT o.case_no, o.client_id, o.staff_id, c.name AS client_name,
       s.name AS staff_name, o.status AS order_status, c.identity_status,
       o.cancel_reason, binding.group_id AS line_group_id, o.contract_identity,
       o.actual_start_date,
       o.actual_end_date, o.deposit_date, o.start_date, o.end_date,
       o.service_days, o.service_hours_per_day, o.deposit_service_days,
       o.floor_fee, o.custom_rest_dates
  FROM orders o
  JOIN clients c ON c.id = o.client_id
  LEFT JOIN staff s ON s.id = o.staff_id
  LEFT JOIN line_order_group_bindings binding ON binding.case_no = o.case_no
 WHERE o.case_no = %s
"""


class MySqlOrderDetailQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_by_case_no(self, case_no: str):
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_DETAIL_SQL, (case_no,))
            return cursor.fetchone()


__all__ = ["MySqlOrderDetailQueryRepository"]

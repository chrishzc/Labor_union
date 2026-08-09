"""MySQL read adapter for Form Management template facts."""

from __future__ import annotations

from typing import Any


_STATISTICS_SQL = """
SELECT
    COALESCE(SUM(CASE WHEN o.status IN ('服務中', '訂單成立') THEN 1 ELSE 0 END), 0)
        AS global_active_orders_count,
    COUNT(DISTINCT CASE WHEN o.status IN ('服務中', '訂單成立') THEN o.staff_id END)
        AS global_active_staff_count,
    COALESCE(SUM(CASE WHEN COALESCE(c.identity_status, '') NOT IN ('', '一般身分', '一般市民') THEN 1 ELSE 0 END), 0)
        AS global_subsidy_orders_count,
    COALESCE(SUM(details.total_employer_self_pay_payable), 0)
        AS global_total_receivable_sum,
    COALESCE(SUM(CASE WHEN o.status NOT IN ('洽談中', '訂單取消')
                  AND c.identity_status <> '非市民'
                  AND o.end_date IS NOT NULL
             THEN 1 ELSE 0 END), 0) AS global_govt_claim_count
  FROM orders o
  JOIN clients c ON c.id = o.client_id
  JOIN v_order_details details ON details.case_no = o.case_no
"""

_CASE_CONTEXT_SQL = """
SELECT o.case_no,
       c.service_time,
       c.service_type,
       c.delivery_type,
       c.residence_type,
       c.city,
       c.identity_status
  FROM orders o
  JOIN clients c ON c.id = o.client_id
 WHERE o.case_no = %s
"""


class MySqlFormManagementQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_statistics(self):
        with self._connection.cursor() as cursor:
            cursor.execute(_STATISTICS_SQL)
            return cursor.fetchone()

    def fetch_case_context(self, case_no: str):
        with self._connection.cursor() as cursor:
            cursor.execute(_CASE_CONTEXT_SQL, (case_no,))
            return cursor.fetchone()


__all__ = ["MySqlFormManagementQueryRepository"]

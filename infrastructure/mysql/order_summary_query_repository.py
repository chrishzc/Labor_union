"""
File: order_summary_query_repository.py
Description: 依 Orders canonical lifecycle scope 提供 bounded 摘要查詢。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from shared_kernel.performance import MAXIMUM_PAGE_SIZE

_ORDER_SUMMARY_PAGE_SQL = """
SELECT o.case_no,
       c.name AS client_name,
       o.status AS order_status,
       o.start_date,
       o.end_date,
       o.actual_start_date,
       o.actual_end_date,
       c.identity_status,
       o.service_days,
       order_details.total_employer_self_pay_payable,
       (
           SELECT GROUP_CONCAT(
                      assigned_staff.name
                      ORDER BY assignment.assignment_sequence
                      SEPARATOR '、'
                  )
             FROM case_staff_assignments assignment
             JOIN staff assigned_staff
               ON assigned_staff.id = assignment.staff_id
            WHERE assignment.case_no = o.case_no
              AND assignment.status <> 'cancelled'
       ) AS staff_name
  FROM orders o FORCE INDEX (PRIMARY)
  JOIN clients c ON c.id = o.client_id
  JOIN v_order_details order_details ON order_details.case_no = o.case_no
 WHERE o.case_no > %s
   AND (%s = 'all' OR o.status NOT IN (%s, %s))
   AND (
       %s IS NULL
       OR o.case_no LIKE CONCAT('%%', %s, '%%')
       OR c.name LIKE CONCAT('%%', %s, '%%')
   )
 ORDER BY o.case_no
 LIMIT %s
"""


class MySqlOrderSummaryQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_page(
        self,
        *,
        after_case_no: str | None,
        page_size: int,
        query_text: str | None,
        lifecycle_scope: OrderLifecycleScope = OrderLifecycleScope.ALL,
    ) -> tuple[Mapping[str, object], ...]:
        cursor_case_no = _cursor_case_no(after_case_no)
        result_limit = _result_limit(page_size)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _ORDER_SUMMARY_PAGE_SQL,
                (
                    cursor_case_no,
                    lifecycle_scope.value,
                    OrderLifecycleStatus.COMPLETED.value,
                    OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED.value,
                    query_text,
                    query_text,
                    query_text,
                    result_limit,
                ),
            )
            return tuple(cursor.fetchall() or ())


def _cursor_case_no(after_case_no: str | None) -> str:
    if after_case_no is None:
        return ""
    if not isinstance(after_case_no, str):
        raise TypeError("after_case_no must be a string or None")
    if not after_case_no or after_case_no.strip() != after_case_no:
        raise ValueError("after_case_no must be canonical")
    if len(after_case_no) > 50:
        raise ValueError("after_case_no exceeds database identity length")
    return after_case_no


def _result_limit(page_size: int) -> int:
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise TypeError("page_size must be an integer")
    if not 1 <= page_size <= MAXIMUM_PAGE_SIZE:
        raise ValueError("page_size is outside the bounded query policy")
    return page_size + 1


__all__ = ["MySqlOrderSummaryQueryRepository"]

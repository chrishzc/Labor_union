"""MySQL adapter for the intentional one-order detail projection."""

from __future__ import annotations

from typing import Any


_ORDER_DETAIL_SQL = """
SELECT o.case_no, o.client_id, o.staff_id, c.name AS client_name,
       COALESCE(
           s.name,
           CASE
                      WHEN o.status IN (
                          '歷史訂單－未服務',
                          '歷史訂單－服務中',
                          '歷史訂單－服務完成',
                          '歷史訂單－帳務完成'
                      ) THEN (
                          SELECT GROUP_CONCAT(
                                     historical_staff.name
                                     ORDER BY historical_pairing.caregiver_ordinal
                                     SEPARATOR '、'
                                 )
                            FROM historical_order_adoption_receipts historical_receipt
                            JOIN historical_order_pairing_evidence historical_pairing
                              ON historical_pairing.receipt_id = historical_receipt.id
                            JOIN staff historical_staff
                              ON historical_staff.id = historical_pairing.staff_id
                           WHERE historical_receipt.id = (
                                 SELECT MAX(latest_historical_receipt.id)
                                   FROM historical_order_adoption_receipts latest_historical_receipt
                                  WHERE latest_historical_receipt.case_no = o.case_no
                                    AND latest_historical_receipt.outcome = 'adopted'
                           )
                             AND historical_pairing.staff_id IS NOT NULL
                             AND historical_pairing.resolution IN (
                                 'evidence_only', 'assignment_candidate', 'assignment_reused'
                             )
                      )
                      ELSE NULL
                      END
       ) AS staff_name, o.status AS order_status, c.identity_status,
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

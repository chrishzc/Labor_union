"""Read the latest adopted Historical Order assertion for timeline overlay."""

from __future__ import annotations

from datetime import date
from typing import Any

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.historical_stage_baseline_overlay import HistoricalStageBaselineFacts


class MySqlHistoricalStageBaselineRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_for_cases(
        self, case_nos: tuple[str, ...]
    ) -> tuple[HistoricalStageBaselineFacts, ...]:
        if not case_nos:
            return ()
        placeholders = ",".join(["%s"] * len(case_nos))
        sql = f"""
SELECT o.case_no,
       o.status,
       o.actual_start_date,
       receipt.id AS adoption_receipt_id
  FROM orders o
  JOIN (
       SELECT case_no, MAX(id) AS receipt_id
         FROM historical_order_adoption_receipts
        WHERE outcome = 'adopted'
          AND case_no IS NOT NULL
        GROUP BY case_no
  ) latest ON latest.case_no = o.case_no
  JOIN historical_order_adoption_receipts receipt
    ON receipt.id = latest.receipt_id
 WHERE o.case_no IN ({placeholders})
 ORDER BY o.case_no
"""
        with self._connection.cursor() as cursor:
            cursor.execute(sql, case_nos)
            rows = tuple(cursor.fetchall() or ())
        return tuple(_facts(row) for row in rows)


def _facts(row) -> HistoricalStageBaselineFacts:
    raw_date = row.get("actual_start_date")
    actual_start = (
        raw_date
        if raw_date is None or type(raw_date) is date
        else date.fromisoformat(str(raw_date))
    )
    return HistoricalStageBaselineFacts(
        str(row["case_no"]),
        int(row["adoption_receipt_id"]),
        OrderLifecycleStatus(str(row["status"])),
        actual_start,
    )


__all__ = ["MySqlHistoricalStageBaselineRepository"]

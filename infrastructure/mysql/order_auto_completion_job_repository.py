"""Bounded MySQL discovery for due canonical Orders completion commands."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.orders.auto_completion_job_dispatch import DueOrderAutoCompletion


class MySqlDueOrderAutoCompletionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def find_due_orders(
        self,
        evaluation_at: datetime,
        after_case_no: str | None,
        limit: int,
    ) -> tuple[DueOrderAutoCompletion, ...]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        evaluation = _naive_taipei_instant(evaluation_at)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _DUE_ORDER_SQL,
                (evaluation, evaluation, after_case_no or "", limit),
            )
            rows = cursor.fetchall()
        return tuple(_due_order(row) for row in rows)


def _naive_taipei_instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evaluation_at must be timezone-aware")
    return value.astimezone(TAIPEI_TIME_ZONE).replace(tzinfo=None)


def _due_order(row: dict[str, Any]) -> DueOrderAutoCompletion:
    completion = row["completion_instant"]
    if not isinstance(completion, datetime):
        raise ValueError("due order completion instant is invalid")
    return DueOrderAutoCompletion(
        case_no=str(row["case_no"]),
        lifecycle_version=int(row["lifecycle_version"]),
        completion_instant=completion.replace(tzinfo=TAIPEI_TIME_ZONE),
        completion_kind=cast(
            Literal["normal", "historical"], str(row["completion_kind"])
        ),
    )


_DUE_ORDER_SQL = """
SELECT due.case_no,due.lifecycle_version,due.completion_instant,due.completion_kind
FROM (
    SELECT
        orders.case_no,
        orders.lifecycle_version,
        CASE
            WHEN MAX(CASE WHEN schedule.work_date = orders.actual_end_date
                           AND schedule.service_hours_override IS NOT NULL THEN 1 ELSE 0 END) = 1
              OR (orders.service_start_time IS NULL AND orders.service_end_time IS NULL
                  AND orders.service_end_day_offset IS NULL)
            THEN TIMESTAMP(orders.actual_end_date, '23:59:59.999999')
            ELSE TIMESTAMP(
                DATE_ADD(orders.actual_end_date, INTERVAL orders.service_end_day_offset DAY),
                orders.service_end_time
            )
        END AS completion_instant,
        'normal' AS completion_kind
    FROM orders
    JOIN scheduling_aggregates aggregate_root
      ON aggregate_root.case_no = orders.case_no
    JOIN scheduling_generations generation
      ON generation.id = aggregate_root.effective_generation_id
     AND generation.case_no = orders.case_no
     AND generation.status = 'effective'
     AND generation.effective_marker = 1
    JOIN staff_schedule schedule
      ON schedule.case_no = orders.case_no
     AND schedule.generation_id = generation.id
     AND schedule.effective_marker = 1
     AND schedule.is_work_day = 1
    LEFT JOIN case_staff_assignments assignment
      ON assignment.id = schedule.assignment_id
     AND assignment.generation_id = generation.id
     AND assignment.status IN ('active', 'planned', 'completed')
    WHERE orders.status = '服務中'
      AND orders.actual_end_date IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM case_staff_assignments invalid_assignment
          WHERE invalid_assignment.generation_id = generation.id
            AND (invalid_assignment.status NOT IN ('active', 'planned', 'completed')
                 OR invalid_assignment.status IS NULL)
      )
      AND NOT EXISTS (
          SELECT 1
          FROM order_lifecycle_control_state control_state
          WHERE control_state.case_no = orders.case_no
            AND control_state.scope = 'auto_complete'
            AND control_state.state = 'active'
      )
    GROUP BY
        orders.case_no,
        orders.lifecycle_version,
        orders.service_days,
        orders.service_hours_per_day,
        orders.actual_end_date,
        orders.service_start_time,
        orders.service_end_time,
        orders.service_end_day_offset
    HAVING COUNT(assignment.id) = COUNT(*)
       AND COUNT(DISTINCT schedule.work_date) = COUNT(*)
       AND (
           (SUM(schedule.service_hours_override IS NOT NULL) = 0
            AND COUNT(*) = orders.service_days)
           OR (SUM(schedule.service_hours_override IS NOT NULL) > 0
               AND orders.service_hours_per_day > 0
               AND SUM(CASE WHEN schedule.service_hours_override IS NOT NULL
                             AND schedule.service_hours_override NOT IN (4, 8) THEN 1 ELSE 0 END) = 0
               AND SUM(COALESCE(schedule.service_hours_override, orders.service_hours_per_day))
                   = orders.service_days * orders.service_hours_per_day)
       )
       AND MAX(schedule.work_date) = orders.actual_end_date
       AND (
           MAX(CASE WHEN schedule.work_date = orders.actual_end_date
                     AND schedule.service_hours_override IS NOT NULL THEN 1 ELSE 0 END) = 1
           OR (orders.service_start_time IS NULL AND orders.service_end_time IS NULL
               AND orders.service_end_day_offset IS NULL)
           OR (orders.service_start_time IS NOT NULL AND orders.service_end_time IS NOT NULL
               AND orders.service_end_day_offset IN (0, 1))
       )
       AND completion_instant <= %s

    UNION ALL

    SELECT
        orders.case_no,
        orders.lifecycle_version,
        TIMESTAMP(DATE_ADD(orders.actual_end_date, INTERVAL 1 DAY), '00:00:00'),
        'historical'
    FROM orders
    WHERE orders.status = '歷史訂單－服務中'
      AND orders.actual_end_date IS NOT NULL
      AND orders.actual_end_date < DATE(%s)
) AS due
WHERE due.case_no > %s
ORDER BY due.case_no
LIMIT %s
"""


__all__ = ["MySqlDueOrderAutoCompletionRepository"]

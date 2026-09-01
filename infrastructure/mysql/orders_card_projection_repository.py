"""
File: orders_card_projection_repository.py
Description: 以單一 bounded SELECT 讀取 Orders 卡片所需的跨域根事實。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared_kernel.performance import MAXIMUM_PAGE_SIZE


_MAXIMUM_ASSIGNMENT_ROWS = 32

_ORDERS_CARD_PROJECTION_SQL = """
SELECT o.case_no,
       o.client_id,
       c.db_updated_at AS client_source_version,
       c.phone,
       c.address,
       o.lifecycle_version,
       o.requires_cooking,
       o.floor_fee,
       o.actual_start_date,
       o.actual_end_date,
       COALESCE(deposit.deposit_obligation_count, 0) AS deposit_obligation_count,
       deposit_projection.contracted_amount_ntd AS deposit_amount_ntd,
       deposit.obligation_identity AS deposit_obligation_identity,
       deposit.obligation_status AS deposit_obligation_status,
       deposit_projection.settlement_state AS deposit_projection_state,
       deposit_projection.allocated_net_amount_ntd AS deposit_allocated_ntd,
       COALESCE(deposit_projection.projection_version,
                deposit.obligation_projection_version) AS deposit_source_version,
       ledger.occurred_on AS deposit_settled_on,
       scheduling.aggregate_version AS scheduling_version,
       assignment.id AS assignment_id,
       assignment.staff_id AS assignment_staff_id,
       assignment.assignment_sequence,
       assignment.assigned_start_date,
       assignment.assigned_end_date,
       assignment.status AS assignment_status,
       assigned_staff.name AS staff_name,
       assigned_staff.updated_at AS staff_source_version
  FROM orders o
  JOIN clients c ON c.id = o.client_id
  LEFT JOIN (
       SELECT obligation.case_no,
              COUNT(*) AS deposit_obligation_count,
              MAX(obligation.obligation_identity) AS obligation_identity,
              MAX(obligation.amount_due_ntd) AS amount_due_ntd,
              MAX(obligation.status) AS obligation_status,
              MAX(obligation.projection_version) AS obligation_projection_version
         FROM client_obligations obligation
        WHERE obligation.obligation_type = 'deposit'
          AND obligation.direction = 'receivable_from_client'
        GROUP BY obligation.case_no
  ) deposit ON deposit.case_no = o.case_no
  LEFT JOIN client_deposit_settlement_projection deposit_projection
    ON deposit_projection.case_no = o.case_no
  LEFT JOIN client_ledger_entries ledger
    ON ledger.id = deposit_projection.latest_ledger_entry_id
  LEFT JOIN scheduling_aggregates scheduling
    ON scheduling.case_no = o.case_no
  LEFT JOIN case_staff_assignments assignment
    ON assignment.case_no = o.case_no
   AND assignment.status IN ('planned', 'active', 'completed')
  LEFT JOIN staff assigned_staff ON assigned_staff.id = assignment.staff_id
 WHERE o.case_no = %s
 ORDER BY assignment.assignment_sequence, assignment.id
 LIMIT %s
"""


class MySqlOrdersCardProjectionRepository:
    """Read-only adapter; it never commits and never opens one query per segment."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_by_case_no(self, case_no: str) -> tuple[Mapping[str, object], ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _ORDERS_CARD_PROJECTION_SQL,
                (case_no, _result_limit()),
            )
            return tuple(cursor.fetchall() or ())


def _result_limit() -> int:
    """Return one sentinel row beyond the accepted assignment slice."""
    if _MAXIMUM_ASSIGNMENT_ROWS + 1 > MAXIMUM_PAGE_SIZE:
        raise RuntimeError("card projection bound exceeds shared query policy")
    return _MAXIMUM_ASSIGNMENT_ROWS + 1


__all__ = ["MySqlOrdersCardProjectionRepository"]

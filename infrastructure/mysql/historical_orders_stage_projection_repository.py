"""Historical-aware lifecycle scope for the existing Orders stage projection SQL."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from infrastructure.mysql.orders_stage_projection_repository import (
    _PAGE_SQL,
    _cursor,
    _limit,
)


_HISTORICAL_SCOPE = """   AND (%s = 'all' OR o.status <> %s)"""
_HISTORICAL_SCOPE_REPLACEMENT = """   AND (
       %s = 'all'
       OR (
           o.status <> %s
           OR (
               o.status = %s
               AND EXISTS (
                   SELECT 1
                     FROM historical_order_adoption_receipts historical_done
                    WHERE historical_done.case_no = o.case_no
                      AND historical_done.outcome = 'adopted'
               )
               AND (
                   completion_fact.receipt_id IS NULL
                   OR COALESCE(client_fact.client_obligation_count, 0) = 0
                   OR COALESCE(client_fact.client_open_count, 0) > 0
                   OR COALESCE(staff_fact.staff_obligation_count, 0) = 0
                   OR COALESCE(staff_fact.staff_open_count, 0) > 0
               )
           )
       )
   )"""

_HISTORICAL_PAGE_SQL = _PAGE_SQL.replace(
    _HISTORICAL_SCOPE,
    _HISTORICAL_SCOPE_REPLACEMENT,
)


class MySqlHistoricalAwareOrdersStageProjectionRepository:
    """Keep cancellations visible and historical Step-11 work actionable."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_page(
        self,
        *,
        after_case_no: str | None,
        page_size: int,
        lifecycle_scope: OrderLifecycleScope = OrderLifecycleScope.ALL,
    ) -> tuple[Mapping[str, object], ...]:
        cursor_identity = _cursor(after_case_no)
        result_limit = _limit(page_size)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _HISTORICAL_PAGE_SQL,
                (
                    cursor_identity,
                    lifecycle_scope.value,
                    OrderLifecycleStatus.COMPLETED.value,
                    OrderLifecycleStatus.COMPLETED.value,
                    result_limit,
                ),
            )
            return tuple(cursor.fetchall() or ())


__all__ = ["MySqlHistoricalAwareOrdersStageProjectionRepository"]

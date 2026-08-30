"""Read adapter connecting LINE order groups to Orders-owned audience facts."""

from __future__ import annotations

from typing import Any

from domains.line.identities import LineUserId
from subsystems.line.order_group_contracts import OrderLineAudience


class MySqlOrdersLineAudienceAdapter:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, case_no: str) -> OrderLineAudience | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_AUDIENCE_SQL, (case_no,))
            order = cursor.fetchone()
            if not order:
                return None
            if str(order["order_status"]) == "訂單取消":
                raise RuntimeError("cancelled_order_cannot_bind_line_group")
            customer_id = str(order.get("customer_line_user_id") or "").strip()
            cursor.execute(_ASSIGNED_STAFF_SQL, (case_no, case_no))
            staff_rows = tuple(cursor.fetchall() or ())
        staff_ids = tuple(
            sorted(
                {
                    str(row["line_user_id"]).strip()
                    for row in staff_rows
                    if str(row.get("line_user_id") or "").strip()
                }
            )
        )
        if not customer_id or not staff_ids:
            raise RuntimeError("order_line_audience_not_ready")
        return OrderLineAudience(
            case_no,
            LineUserId(customer_id),
            tuple(LineUserId(value) for value in staff_ids),
        )

_ORDER_AUDIENCE_SQL = (
    "SELECT o.case_no,o.status AS order_status,c.line_user_id AS customer_line_user_id "
    "FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s FOR UPDATE"
)
_ASSIGNED_STAFF_SQL = (
    "SELECT DISTINCT s.line_user_id FROM staff s JOIN ("
    "SELECT a.staff_id FROM case_staff_assignments a WHERE a.case_no=%s "
    "AND a.status IN ('planned','active') UNION SELECT o.staff_id FROM orders o "
    "WHERE o.case_no=%s AND o.staff_id IS NOT NULL) assigned ON assigned.staff_id=s.id"
)
__all__ = ["MySqlOrdersLineAudienceAdapter"]

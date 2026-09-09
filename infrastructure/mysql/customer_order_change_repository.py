"""Read-only MySQL adapter for customer-bound order-change intake."""

from __future__ import annotations

from typing import Any

from subsystems.line.customer_order_change_contracts import CustomerOrderSnapshot


class MySqlCustomerOrderChangeRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_for_client(self, client_id: int) -> tuple[CustomerOrderSnapshot, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_SELECT + " WHERE o.client_id=%s ORDER BY o.created_at DESC,o.case_no DESC", (client_id,))
            return tuple(_snapshot(row) for row in cursor.fetchall() or ())

    def load_for_client(
        self, client_id: int, case_no: str, *, lock: bool = False
    ) -> CustomerOrderSnapshot | None:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                _ORDER_SELECT + " WHERE o.client_id=%s AND o.case_no=%s" + suffix,
                (client_id, case_no),
            )
            row = cursor.fetchone()
        return _snapshot(row) if row else None


def _snapshot(row: dict[str, Any]) -> CustomerOrderSnapshot:
    cooking = row.get("requires_cooking")
    values = {
        "service_city": str(row.get("service_city") or ""),
        "service_address": str(row.get("service_address") or ""),
        "residence_type": str(row.get("residence_type") or ""),
        "requires_cooking": "未設定" if cooking is None else "需要" if bool(cooking) else "不需要",
        "start_date": str(row.get("start_date") or ""),
        "end_date": str(row.get("end_date") or ""),
        "service_days": str(row.get("service_days") or ""),
        "service_start_time": str(row.get("service_start_time") or ""),
        "service_end_time": str(row.get("service_end_time") or ""),
        "service_end_day_offset": str(row.get("service_end_day_offset") or "0"),
    }
    return CustomerOrderSnapshot(
        str(row["case_no"]),
        str(row["status"]),
        int(row.get("order_version") or 0),
        int(row.get("client_profile_version") or 0),
        values,
    )


_ORDER_SELECT = (
    "SELECT o.case_no,o.status,o.lifecycle_version AS order_version,"
    "o.start_date,o.end_date,o.service_days,o.service_start_time,o.service_end_time,"
    "o.service_end_day_offset,o.requires_cooking,c.city AS service_city,"
    "c.address AS service_address,c.residence_type,"
    "c.client_profile_version "
    "FROM orders o JOIN clients c ON c.id=o.client_id"
)


__all__ = ["MySqlCustomerOrderChangeRepository"]

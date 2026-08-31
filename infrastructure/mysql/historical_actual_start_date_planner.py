"""MySQL facts adapter for historical actual-start official-date rebuilding."""

from __future__ import annotations

from datetime import date

from domains.orders.actual_start import calculate_service_dates


class MySqlHistoricalActualStartDatePlanner:
    def __init__(self, connection) -> None:
        self._connection = connection

    def calculate(
        self,
        case_no: str,
        actual_start_date: date,
        *,
        for_update: bool,
    ) -> tuple[date, ...]:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.service_type,o.service_days FROM orders o "
                "JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s" + suffix,
                (case_no,),
            )
            order = cursor.fetchone()
            if order is None:
                raise ValueError("historical_actual_start_order_not_found")
            cursor.execute(
                "SELECT holiday_date FROM holidays WHERE holiday_date >= %s "
                "ORDER BY holiday_date" + suffix,
                (actual_start_date,),
            )
            holiday_dates = tuple(row["holiday_date"] for row in cursor.fetchall())
        return calculate_service_dates(
            actual_start_date,
            int(order["service_days"]),
            _canonical_service_mode(str(order["service_type"])),
            holiday_dates,
        )


def _canonical_service_mode(value: str) -> str:
    aliases = {
        "週休一日": "週休1日",
        "休周日": "週休1日",
        "週休二日": "週休2日",
        "周休二日": "週休2日",
    }
    return aliases.get(value.strip(), value.strip())


__all__ = ["MySqlHistoricalActualStartDatePlanner"]

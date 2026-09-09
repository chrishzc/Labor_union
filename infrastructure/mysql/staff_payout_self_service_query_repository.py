"""MySQL adapter for the canonical staff payout self-service read model."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from subsystems.staff_payables.staff_payout_self_service_query import (
    StaffPayoutItemView,
    StaffPayoutTransactionView,
)


class MySqlStaffPayoutSelfServiceRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def query_by_staff_and_payment_month(
        self, staff_id: int, year: int, month: int
    ) -> tuple[StaffPayoutItemView, ...]:
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        with self._connection.cursor() as cursor:
            cursor.execute(_SUMMARY_SQL, (staff_id, start, end))
            summaries = tuple(cursor.fetchall())
            if not summaries:
                return ()
            cursor.execute(_TRANSACTIONS_SQL, (staff_id, start, end))
            transactions_by_item: dict[
                tuple[int, str, date], list[StaffPayoutTransactionView]
            ] = {}
            for row in cursor.fetchall():
                key = (
                    int(row["assignment_id"]),
                    str(row["case_no"]),
                    _date(row["due_date"]),
                )
                event_type = str(row["event_type"])
                amount = Decimal(str(row["allocated_amount_ntd"]))
                if event_type in {"return", "reversal"}:
                    amount = -amount
                transactions_by_item.setdefault(key, []).append(
                    StaffPayoutTransactionView(
                        transaction_type=event_type,
                        transaction_status="succeeded",
                        amount=amount,
                        occurred_at=_date(row["occurred_on"]),
                    )
                )
        return tuple(
            _item(row, transactions_by_item)
            for row in summaries
        )


def _item(row, transactions_by_item) -> StaffPayoutItemView:
    key = (
        int(row["assignment_id"]),
        str(row["case_no"]),
        _date(row["due_date"]),
    )
    transactions = tuple(transactions_by_item.get(key, ()))
    payout_dates = [
        item.occurred_at
        for item in transactions
        if item.transaction_type == "payout"
    ]
    return StaffPayoutItemView(
        assignment_id=key[0],
        case_no=key[1],
        staff_id=int(row["staff_id"]),
        total_payable=Decimal(str(row["total_payable_ntd"])),
        amount_paid=Decimal(str(row["net_paid_ntd"])),
        due_date=key[2],
        paid_at=max(payout_dates) if payout_dates else None,
        payment_status=str(row["payment_status"]),
        transactions=transactions,
    )


def _date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).split(" ", 1)[0])


_SUMMARY_SQL = """
SELECT obligations.assignment_id,
       obligations.case_no,
       obligations.staff_id,
       obligations.due_date,
       SUM(COALESCE(projection.obligation_amount_ntd, obligations.amount_due_ntd)) AS total_payable_ntd,
       SUM(COALESCE(projection.net_paid_ntd, 0)) AS net_paid_ntd,
       CASE
         WHEN SUM(CASE WHEN COALESCE(projection.status, 'payable') = 'anomaly' THEN 1 ELSE 0 END) > 0 THEN 'anomaly'
         WHEN SUM(COALESCE(projection.balance_ntd, obligations.amount_due_ntd)) = 0 THEN 'completed'
         ELSE 'payable'
       END AS payment_status
FROM staff_obligations obligations
LEFT JOIN staff_payable_projections projection
  ON projection.obligation_identity = obligations.obligation_identity
WHERE obligations.staff_id = %s
  AND obligations.due_date BETWEEN %s AND %s
  AND obligations.direction = 'payable_to_staff'
  AND obligations.status <> 'cancelled'
GROUP BY obligations.assignment_id, obligations.case_no, obligations.staff_id, obligations.due_date
ORDER BY obligations.due_date ASC, obligations.case_no ASC, obligations.assignment_id ASC
"""


_TRANSACTIONS_SQL = """
SELECT obligations.assignment_id,
       obligations.case_no,
       obligations.due_date,
       events.id AS payout_event_id,
       events.event_type,
       events.occurred_on,
       SUM(links.allocated_amount_ntd) AS allocated_amount_ntd
FROM staff_obligations obligations
JOIN staff_payout_obligation_links links
  ON links.obligation_identity = obligations.obligation_identity
JOIN staff_payout_events events
  ON events.id = links.payout_event_id
WHERE obligations.staff_id = %s
  AND obligations.due_date BETWEEN %s AND %s
  AND obligations.direction = 'payable_to_staff'
  AND obligations.status <> 'cancelled'
GROUP BY obligations.assignment_id, obligations.case_no, obligations.due_date,
         events.id, events.event_type, events.occurred_on
ORDER BY events.occurred_on ASC, events.id ASC
"""


__all__ = ["MySqlStaffPayoutSelfServiceRepository"]

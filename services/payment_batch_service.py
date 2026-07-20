"""Read-only preparation of monthly staff settlement bank transfers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any

from services.db_service import get_connection


def _month_start(target_month: str) -> date:
    if not isinstance(target_month, str) or not re.fullmatch(
        r"\d{4}-(0[1-9]|1[0-2])", target_month
    ):
        raise ValueError("Invalid target_month format. Expected 'YYYY-MM'.")
    return datetime.strptime(target_month, "%Y-%m").date().replace(day=1)


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def prepare_monthly_payments(target_month: str) -> list[dict]:
    """Return one payable row per finalized monthly staff settlement.

    The salary month comes exclusively from ``settlement_month``.  Bank dates
    are not used to infer it, and this read-only preparation never creates a
    transfer or changes a settlement.
    """
    settlement_month = _month_start(target_month)
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT sms.id AS settlement_id,
                       sms.staff_id,
                       sms.total_payable,
                       sms.total_paid,
                       smsd.staff_payment_id,
                       smsd.case_no,
                       sp.due_date
                FROM staff_monthly_settlements sms
                JOIN staff_monthly_settlement_details smsd
                  ON smsd.settlement_id = sms.id
                JOIN staff_payments sp
                  ON sp.id = smsd.staff_payment_id
                WHERE sms.settlement_month = %s
                  AND sms.status IN ('finalized', 'partially_paid')
                  AND sms.total_payable - sms.total_paid > 0
                ORDER BY sms.id, smsd.id
                """,
                (settlement_month,),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        settlement_id = int(row["settlement_id"])
        group = grouped.setdefault(
            settlement_id,
            {
                "settlement_id": settlement_id,
                "staff_id": int(row["staff_id"]),
                "total_payable": _money(row["total_payable"]),
                "total_paid": _money(row["total_paid"]),
                "case_nos": [],
                "staff_payment_ids": [],
                "due_dates": set(),
                "missing_due_date": False,
            },
        )
        if int(row["staff_id"]) != group["staff_id"]:
            raise ValueError("settlement details contain inconsistent staff_id")

        staff_payment_id = int(row["staff_payment_id"])
        if staff_payment_id not in group["staff_payment_ids"]:
            group["staff_payment_ids"].append(staff_payment_id)
        case_no = str(row["case_no"])
        if case_no not in group["case_nos"]:
            group["case_nos"].append(case_no)

        due_date = row["due_date"]
        if due_date is None:
            group["missing_due_date"] = True
        else:
            group["due_dates"].add(due_date)

    preparation_rows = []
    for group in grouped.values():
        remaining = group["total_payable"] - group["total_paid"]
        if (
            remaining <= 0
            or group["missing_due_date"]
            or len(group["due_dates"]) != 1
        ):
            continue
        transfer_date = next(iter(group.pop("due_dates")))
        group.pop("missing_due_date")
        preparation_rows.append(
            {
                **group,
                "transfer_date": transfer_date,
                "remaining_amount": remaining,
            }
        )

    return preparation_rows

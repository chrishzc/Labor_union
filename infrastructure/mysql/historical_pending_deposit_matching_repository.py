"""Persist a historical pending-deposit match into Scheduling-owned plan roots."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Mapping

from subsystems.scheduling.historical_pending_deposit_matching import (
    HistoricalPendingDepositMatchCommand,
    HistoricalPendingDepositMatchReceipt,
)


class HistoricalPendingDepositMatchingConflict(ValueError):
    """Current Matching roots cannot be safely replaced by historical evidence."""


class MySqlHistoricalPendingDepositMatchingRepository:
    """Use a borrowed connection; the historical workbook owns commit/rollback."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def ensure_pending_deposit_match(
        self,
        command: HistoricalPendingDepositMatchCommand,
    ) -> HistoricalPendingDepositMatchReceipt:
        with _cursor(self._connection) as cursor:
            order = _one(
                cursor,
                "SELECT case_no,status,start_date,end_date FROM orders "
                "WHERE case_no=%s FOR UPDATE",
                (command.case_no,),
            )
            if order is None or order.get("case_no") != command.case_no:
                raise HistoricalPendingDepositMatchingConflict(
                    "historical_matching_case_not_found"
                )
            if order.get("status") != "洽談中":
                raise HistoricalPendingDepositMatchingConflict(
                    "historical_matching_order_status_conflict"
                )
            planned_start = _date(order.get("start_date"), "start_date")
            planned_end = _date(order.get("end_date"), "end_date")
            if planned_start > planned_end:
                raise HistoricalPendingDepositMatchingConflict(
                    "historical_matching_planned_interval_invalid"
                )

            plans = _rows(
                cursor,
                "SELECT id,version,status,is_active,start_date,end_date "
                "FROM caregiver_matching_plans WHERE case_no=%s "
                "ORDER BY version DESC FOR UPDATE",
                (command.case_no,),
            )
            active = tuple(row for row in plans if row.get("is_active") == 1)
            if len(active) > 1:
                raise HistoricalPendingDepositMatchingConflict(
                    "historical_matching_active_plan_ambiguous"
                )
            if active:
                existing = active[0]
                segments = _rows(
                    cursor,
                    "SELECT segment_order,staff_id,assigned_start_date,assigned_end_date "
                    "FROM caregiver_matching_plan_segments WHERE plan_id=%s "
                    "ORDER BY segment_order,id FOR UPDATE",
                    (existing["id"],),
                )
                if _is_exact_pending_plan(
                    existing,
                    segments,
                    command.staff_id,
                    planned_start,
                    planned_end,
                ):
                    return HistoricalPendingDepositMatchReceipt(
                        command.case_no,
                        int(existing["id"]),
                        int(existing["version"]),
                        command.staff_id,
                        False,
                    )
                raise HistoricalPendingDepositMatchingConflict(
                    "historical_matching_current_plan_conflict"
                )

            version = max((int(row["version"]) for row in plans), default=0) + 1
            cursor.execute(
                "INSERT INTO caregiver_matching_plans "
                "(case_no,version,status,is_active,start_date,end_date,created_by) "
                "VALUES (%s,%s,'proposed',1,%s,%s,%s)",
                (
                    command.case_no,
                    version,
                    planned_start,
                    planned_end,
                    command.actor,
                ),
            )
            plan_id = cursor.lastrowid
            if isinstance(plan_id, bool) or not isinstance(plan_id, int) or plan_id <= 0:
                raise RuntimeError("historical_matching_plan_insert_failed")
            cursor.execute(
                "INSERT INTO caregiver_matching_plan_segments "
                "(plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date) "
                "VALUES (%s,1,%s,%s,%s)",
                (plan_id, command.staff_id, planned_start, planned_end),
            )
            return HistoricalPendingDepositMatchReceipt(
                command.case_no,
                plan_id,
                version,
                command.staff_id,
                True,
            )


def _is_exact_pending_plan(
    plan: Mapping[str, object],
    segments: tuple[Mapping[str, object], ...],
    staff_id: int,
    planned_start: date,
    planned_end: date,
) -> bool:
    return (
        plan.get("status") == "proposed"
        and _date(plan.get("start_date"), "plan start_date") == planned_start
        and _date(plan.get("end_date"), "plan end_date") == planned_end
        and len(segments) == 1
        and int(segments[0].get("segment_order") or 0) == 1
        and int(segments[0].get("staff_id") or 0) == staff_id
        and _date(segments[0].get("assigned_start_date"), "segment start_date")
        == planned_start
        and _date(segments[0].get("assigned_end_date"), "segment end_date")
        == planned_end
    )


def _date(value: object, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise HistoricalPendingDepositMatchingConflict(
                "historical_matching_planned_interval_invalid"
            ) from error
    raise HistoricalPendingDepositMatchingConflict(
        f"historical_matching_{field_name.replace(' ', '_')}_missing"
    )


def _one(cursor: Any, statement: str, parameters: tuple[object, ...]):
    cursor.execute(statement, parameters)
    row = cursor.fetchone()
    if row is not None and not isinstance(row, Mapping):
        raise TypeError("historical matching row must be a mapping")
    return row


def _rows(
    cursor: Any,
    statement: str,
    parameters: tuple[object, ...],
) -> tuple[Mapping[str, object], ...]:
    cursor.execute(statement, parameters)
    rows = tuple(cursor.fetchall() or ())
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("historical matching rows must be mappings")
    return rows


@contextmanager
def _cursor(connection: Any):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


__all__ = [
    "HistoricalPendingDepositMatchingConflict",
    "MySqlHistoricalPendingDepositMatchingRepository",
]

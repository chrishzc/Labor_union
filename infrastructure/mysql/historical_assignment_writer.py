"""Scheduling-owned writer for purpose-specific historical assignments."""

from __future__ import annotations

from datetime import date

from subsystems.orders.historical_adoption_workflow import (
    SchedulingHistoricalAssignmentPort,
)


class MySqlHistoricalAssignmentWriter(SchedulingHistoricalAssignmentPort):
    """Write completed historical assignments on a caller-owned connection."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def append_completed_assignments(
        self,
        case_no: str,
        assignments: tuple[tuple[int, date, date], ...],
    ) -> tuple[int, ...]:
        if not assignments:
            return ()
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(assignment_sequence),0) AS last_sequence "
                "FROM case_staff_assignments WHERE case_no=%s FOR UPDATE",
                (case_no,),
            )
            sequence = int(cursor.fetchone()["last_sequence"])
            identifiers: list[int] = []
            for staff_id, start_date, end_date in assignments:
                sequence += 1
                cursor.execute(
                    "INSERT INTO case_staff_assignments "
                    "(case_no,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,"
                    "original_assigned_start_date,original_assigned_end_date,status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'completed')",
                    (
                        case_no,
                        staff_id,
                        sequence,
                        start_date,
                        end_date,
                        start_date,
                        end_date,
                    ),
                )
                identifiers.append(int(cursor.lastrowid))
        return tuple(identifiers)


__all__ = ["MySqlHistoricalAssignmentWriter"]

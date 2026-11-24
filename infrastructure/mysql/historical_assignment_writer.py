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

    def retire_adopted_assignments(
        self, case_no: str, assignment_ids: tuple[int, ...],
    ) -> None:
        """Retire the locked effective rows while retaining their adoption links."""
        if not assignment_ids:
            return
        placeholders = ",".join("%s" for _ in assignment_ids)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE case_staff_assignments SET status='cancelled' "
                "WHERE case_no=%s AND generation_id IS NULL "
                "AND status IN ('planned','active','completed') "
                f"AND id IN ({placeholders})",
                (case_no, *assignment_ids),
            )
            if cursor.rowcount != len(assignment_ids):
                raise RuntimeError("historical_unserved_assignment_conflict")


__all__ = ["MySqlHistoricalAssignmentWriter"]

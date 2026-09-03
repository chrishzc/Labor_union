"""MySQL adapter for historical calendar assignment-only remediation."""

from __future__ import annotations

from datetime import date

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.admin_command_repository import AdminCommandRepository
from infrastructure.mysql.historical_assignment_writer import (
    MySqlHistoricalAssignmentWriter,
)
from subsystems.orders.historical_calendar_assignment_remediation import (
    HistoricalCalendarAssignmentCaseFacts,
)


class MySqlHistoricalCalendarAssignmentRemediationRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._receipts = AdminCommandRepository(connection)
        self._writer = MySqlHistoricalAssignmentWriter(connection)

    def load_case(self, case_no: str, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.case_no,o.status,o.lifecycle_version,c.name AS client_name "
                "FROM orders o JOIN clients c ON c.id=o.client_id "
                "WHERE o.case_no=%s" + suffix,
                (case_no,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return HistoricalCalendarAssignmentCaseFacts(
            case_no=str(row["case_no"]),
            client_name=str(row["client_name"]),
            status=OrderLifecycleStatus(str(row["status"])),
            lifecycle_version=int(row["lifecycle_version"]),
        )

    def resolve_staff(self, name: str, *, for_update: bool) -> tuple[int, ...]:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM staff WHERE name=%s ORDER BY id" + suffix,
                (name,),
            )
            return tuple(int(row["id"]) for row in cursor.fetchall())

    def find_matching_completed_assignment(
        self,
        case_no: str,
        staff_id: int,
        start_date: date,
        end_date: date,
        *,
        for_update: bool,
    ):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM case_staff_assignments "
                "WHERE case_no=%s AND staff_id=%s AND status='completed' "
                "AND assigned_start_date=%s "
                "AND assigned_end_date IS NOT NULL AND assigned_end_date>=%s "
                "ORDER BY assigned_end_date,id LIMIT 1" + suffix,
                (case_no, staff_id, start_date, end_date),
            )
            row = cursor.fetchone()
        return None if row is None else int(row["id"])

    def append_completed_assignment(
        self,
        case_no: str,
        staff_id: int,
        start_date: date,
        end_date: date,
    ) -> int:
        identifiers = self._writer.append_completed_assignments(
            case_no,
            ((staff_id, start_date, end_date),),
        )
        if len(identifiers) != 1:
            raise RuntimeError("historical_calendar_assignment_write_failed")
        return identifiers[0]

    def load_receipt(self, family: str, key: str):
        return self._receipts.load_receipt(family, key)

    def save_receipt(
        self,
        family: str,
        key: str,
        request_fingerprint: str,
        preview_fingerprint: str,
        actor: str,
        reason: str,
        result: dict[str, object],
    ) -> None:
        self._receipts.save_receipt(
            family,
            key,
            request_fingerprint,
            preview_fingerprint,
            actor,
            reason,
            result,
        )


__all__ = ["MySqlHistoricalCalendarAssignmentRemediationRepository"]

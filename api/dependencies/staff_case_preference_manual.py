"""Request-scoped Staff six-relation manual workflow."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_case_preference_manual_repository import MySqlStaffCasePreferenceManualRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.staff.case_preference_manual_workflow import StaffCasePreferenceManualWorkflow


@dataclass(slots=True)
class StaffCasePreferenceManualApplication:
    workflow: StaffCasePreferenceManualWorkflow


def get_staff_case_preference_manual_application():
    connection = get_connection()
    try:
        yield StaffCasePreferenceManualApplication(
            StaffCasePreferenceManualWorkflow(
                MySqlStaffCasePreferenceManualRepository(connection),
                lambda: MySqlUnitOfWork(connection),
            )
        )
    finally:
        connection.close()


__all__ = ["StaffCasePreferenceManualApplication", "get_staff_case_preference_manual_application"]

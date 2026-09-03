"""Request-scoped construction for Staff case-preference query and mutation workflows."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_case_preference_summary_mutation_repository import (
    MySqlStaffCasePreferenceMutationRepository,
)
from infrastructure.mysql.staff_case_preference_summary_query_repository import (
    MySqlStaffCasePreferenceSummaryQueryRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.staff.case_preference_summary_mutation import StaffCasePreferenceMutationWorkflow
from subsystems.staff.case_preference_summary_query import StaffCasePreferenceSummaryQueryApplication


def get_staff_case_preference_summary_application():
    connection = get_connection()
    try:
        yield StaffCasePreferenceSummaryQueryApplication(
            MySqlStaffCasePreferenceSummaryQueryRepository(connection)
        )
    finally:
        connection.close()


def get_staff_case_preference_mutation_workflow():
    connection = get_connection()
    repository = MySqlStaffCasePreferenceMutationRepository(connection)
    workflow = StaffCasePreferenceMutationWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
    )
    try:
        yield workflow
    finally:
        connection.close()


__all__ = [
    "get_staff_case_preference_mutation_workflow",
    "get_staff_case_preference_summary_application",
]

"""Per-request composition for Staff Profile and Bank owner mutations."""

from __future__ import annotations

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_bank_account_repository import MySqlStaffBankAccountRepository
from infrastructure.mysql.staff_profile_mutation_repository import MySqlStaffProfileMutationRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.staff.bank_account_workflow import StaffBankAccountWorkflow
from subsystems.staff.profile_workflow import StaffProfileMutationWorkflow


def get_staff_profile_mutation_workflow():
    connection = get_connection()
    try:
        yield StaffProfileMutationWorkflow(
            MySqlStaffProfileMutationRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


def get_staff_bank_account_workflow():
    connection = get_connection()
    try:
        yield StaffBankAccountWorkflow(
            MySqlStaffBankAccountRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


__all__ = ["get_staff_bank_account_workflow", "get_staff_profile_mutation_workflow"]

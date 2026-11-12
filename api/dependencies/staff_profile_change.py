"""Compose the existing Staff writers on one connection for LIFF review."""
from contextlib import contextmanager
from functools import lru_cache

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_bank_account_repository import MySqlStaffBankAccountRepository
from infrastructure.mysql.staff_case_preference_manual_repository import MySqlStaffCasePreferenceManualRepository
from infrastructure.mysql.staff_matching_preference_repository import MySqlStaffMatchingPreferenceRepository
from infrastructure.mysql.staff_profile_mutation_repository import MySqlStaffProfileMutationRepository
from infrastructure.mysql.staff_qualification_editing_repository import MySqlStaffQualificationEditingRepository
from infrastructure.mysql.staff_retirement_repository import MySqlStaffRetirementRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.redis.registration_connection import registration_redis_client
from infrastructure.redis.staff_profile_change_staging import StaffProfileChangeStaging
from subsystems.scheduling.staff_matching_preference_workflow import StaffMatchingPreferenceWorkflow
from subsystems.staff.bank_account_workflow import StaffBankAccountWorkflow
from subsystems.staff.case_preference_manual_workflow import StaffCasePreferenceManualWorkflow
from subsystems.staff.profile_change_approval import StaffProfileChangeApproval
from subsystems.staff.profile_workflow import StaffProfileMutationWorkflow
from subsystems.staff.qualification_editing_workflow import StaffQualificationEditingWorkflow


@contextmanager
def staff_profile_change_application():
    connection = get_connection()
    try:
        def uow():
            return MySqlUnitOfWork(connection)

        yield StaffProfileChangeApproval(
            uow,
            StaffProfileMutationWorkflow(MySqlStaffProfileMutationRepository(connection), uow),
            StaffBankAccountWorkflow(MySqlStaffBankAccountRepository(connection), uow),
            StaffCasePreferenceManualWorkflow(MySqlStaffCasePreferenceManualRepository(connection), uow),
            StaffQualificationEditingWorkflow(MySqlStaffQualificationEditingRepository(connection), uow),
            StaffMatchingPreferenceWorkflow(MySqlStaffMatchingPreferenceRepository(connection), uow),
        ), MySqlStaffRetirementRepository(connection)
    finally:
        connection.close()


@lru_cache(maxsize=1)
def staff_profile_change_staging():
    return StaffProfileChangeStaging(registration_redis_client(role="admin"))

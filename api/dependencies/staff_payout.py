"""
File: staff_payout.py
Description: 建立 Staff Payables 付款、追償與唯讀查詢的 request-scoped dependencies。
"""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.staff_payout_repository import (
    MySqlStaffPayoutRepository,
    StaffPayoutMySqlUnitOfWork,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_overpayment_recovery_repository import MySqlStaffOverpaymentRecoveryRepository
from subsystems.staff_payables.overpayment_recovery import StaffOverpaymentRecoveryWorkflow
from subsystems.staff_payables.overpayment_recovery_matching import StaffOverpaymentRecoveryMatchingWorkflow
from subsystems.staff_payables.overpayment_recovery_query import StaffOverpaymentRecoveryQueryService
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutReconciliationWorkflow,
    StaffPayoutSelection,
)


@dataclass(slots=True)
class StaffPayoutApplication:
    repository: MySqlStaffPayoutRepository
    workflow: StaffPayoutReconciliationWorkflow

    def query(self, staff_id: int):
        return self.repository.query_staff_payables(staff_id)

    def query_payout_difference_source(self, identity: str):
        return self.repository.query_payout_difference_source(identity)

    def preview(self, selection: StaffPayoutSelection, correlation_id):
        return self.workflow.preview(selection, correlation_id)

    def apply(self, request: StaffPayoutApplyRequest):
        self.repository.bind_apply_request(request)
        try:
            return self.workflow.apply(request)
        finally:
            self.repository.clear_apply_request()


def get_staff_payout_application():
    connection = get_connection()
    try:
        yield build_staff_payout_application(connection)
    finally:
        connection.close()


def build_staff_payout_application(connection):
    repository = MySqlStaffPayoutRepository(connection)
    workflow = StaffPayoutReconciliationWorkflow(
        repository,
        lambda: StaffPayoutMySqlUnitOfWork(connection),
    )
    return StaffPayoutApplication(repository, workflow)


def get_staff_overpayment_recovery_application():
    connection = get_connection()
    try:
        yield StaffOverpaymentRecoveryWorkflow(
            MySqlStaffOverpaymentRecoveryRepository(connection),
            lambda: StaffPayoutMySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


def get_staff_overpayment_recovery_matching_application():
    connection = get_connection()
    try:
        yield StaffOverpaymentRecoveryMatchingWorkflow(
            MySqlStaffOverpaymentRecoveryRepository(connection),
            lambda: StaffPayoutMySqlUnitOfWork(connection),
        )
    finally:
        connection.close()


def get_staff_overpayment_recovery_query_application():
    connection = get_connection()
    try:
        yield StaffOverpaymentRecoveryQueryService(
            MySqlStaffOverpaymentRecoveryRepository(connection)
        )
    finally:
        connection.close()


__all__ = [
    "StaffPayoutApplication",
    "build_staff_payout_application",
    "get_staff_payout_application",
    "get_staff_overpayment_recovery_query_application",
]

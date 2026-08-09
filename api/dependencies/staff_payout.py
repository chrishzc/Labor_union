"""Per-request construction for Staff Payout Reconciliation."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.staff_payout_repository import (
    MySqlStaffPayoutRepository,
    StaffPayoutMySqlUnitOfWork,
)
from infrastructure.mysql.mysql_adapter import get_connection
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


__all__ = [
    "StaffPayoutApplication",
    "build_staff_payout_application",
    "get_staff_payout_application",
]

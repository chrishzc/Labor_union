"""Composition root for client refund-overpayment recovery collection."""

from dataclasses import dataclass

from infrastructure.mysql.client_over_refund_recovery_repository import (
    ClientRefundReversalMySqlUnitOfWork, MySqlClientOverRefundRecoveryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.client_finance.over_refund_recovery_workflow import ClientOverRefundRecoveryWorkflow
from subsystems.client_finance.over_refund_recovery_matching_workflow import (
    ClientOverRefundRecoveryMatchingWorkflow,
)


@dataclass(slots=True)
class ClientOverRefundRecoveryApplication:
    workflow: ClientOverRefundRecoveryWorkflow
    matching_workflow: ClientOverRefundRecoveryMatchingWorkflow

    def preview(self, selection, correlation_id):
        return self.workflow.preview(selection, correlation_id)

    def apply(self, request):
        return self.workflow.apply(request)

    def preview_matching(self, selection, correlation_id):
        return self.matching_workflow.preview(selection, correlation_id)

    def apply_matching(self, request):
        return self.matching_workflow.apply(request)


def get_client_over_refund_recovery_application():
    connection = get_connection()
    repository = MySqlClientOverRefundRecoveryRepository(connection)
    try:
        unit_of_work = lambda: ClientRefundReversalMySqlUnitOfWork(connection)
        yield ClientOverRefundRecoveryApplication(
            ClientOverRefundRecoveryWorkflow(repository, unit_of_work),
            ClientOverRefundRecoveryMatchingWorkflow(repository, unit_of_work),
        )
    finally:
        connection.close()

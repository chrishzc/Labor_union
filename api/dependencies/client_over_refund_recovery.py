"""
File: client_over_refund_recovery.py
Description: 建立客戶退款超額追償的 owner workflows 與唯讀 Query。
"""

from dataclasses import dataclass

from infrastructure.mysql.client_over_refund_recovery_repository import (
    ClientRefundReversalMySqlUnitOfWork, MySqlClientOverRefundRecoveryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.client_finance.over_refund_recovery_workflow import ClientOverRefundRecoveryWorkflow
from subsystems.client_finance.over_refund_recovery_matching_workflow import (
    ClientOverRefundRecoveryMatchingWorkflow,
)
from subsystems.client_finance.client_over_refund_recovery_query import (
    ClientOverRefundRecoveryQuerySelection,
    ClientOverRefundRecoveryQueryWorkflow,
)


@dataclass(slots=True)
class ClientOverRefundRecoveryApplication:
    workflow: ClientOverRefundRecoveryWorkflow
    matching_workflow: ClientOverRefundRecoveryMatchingWorkflow
    query_workflow: ClientOverRefundRecoveryQueryWorkflow

    def preview(self, selection, correlation_id):
        return self.workflow.preview(selection, correlation_id)

    def apply(self, request):
        return self.workflow.apply(request)

    def preview_matching(self, selection, correlation_id):
        return self.matching_workflow.preview(selection, correlation_id)

    def apply_matching(self, request):
        return self.matching_workflow.apply(request)

    def query_recovery(self, selection: ClientOverRefundRecoveryQuerySelection, correlation_id):
        return self.query_workflow.query(selection, correlation_id)


def get_client_over_refund_recovery_application():
    connection = get_connection()
    repository = MySqlClientOverRefundRecoveryRepository(connection)
    try:
        unit_of_work = lambda: ClientRefundReversalMySqlUnitOfWork(connection)
        yield ClientOverRefundRecoveryApplication(
            ClientOverRefundRecoveryWorkflow(repository, unit_of_work),
            ClientOverRefundRecoveryMatchingWorkflow(repository, unit_of_work),
            ClientOverRefundRecoveryQueryWorkflow(repository),
        )
    finally:
        connection.close()

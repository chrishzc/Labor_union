"""
File: historical_order_review_remediation.py
Description: 建立每次請求專用的歷史訂單 review 更正 application。
"""

from __future__ import annotations

from infrastructure.mysql.historical_order_adoption_repository import MySqlHistoricalOrderAdoptionRepository
from infrastructure.mysql.historical_assignment_writer import MySqlHistoricalAssignmentWriter
from infrastructure.mysql.historical_pending_deposit_matching_repository import (
    MySqlHistoricalPendingDepositMatchingRepository,
)
from infrastructure.mysql.historical_order_review_remediation_repository import (
    HistoricalOrderReviewRemediationMySqlUnitOfWork,
    MySqlHistoricalOrderReviewRemediationRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.orders.historical_adoption_workflow import HistoricalOrderAdoptionWorkflow
from subsystems.orders.historical_review_remediation_workflow import HistoricalReviewRemediationWorkflow


class HistoricalOrderReviewRemediationApplication:
    def __init__(self, workflow: HistoricalReviewRemediationWorkflow):
        self.workflow = workflow

    def query(self, review_identity, correlation_id):
        return self.workflow.query(review_identity, correlation_id)

    def preview(
        self,
        review_identity,
        source_path,
        expected_review_version,
        expected_remediation_version,
        actor,
        reason,
        evidence,
        correlation_id,
    ):
        return self.workflow.preview(
            review_identity,
            source_path,
            expected_review_version,
            expected_remediation_version,
            actor,
            reason,
            evidence,
            correlation_id,
        )

    def apply(self, command):
        return self.workflow.apply(command)


def get_historical_order_review_remediation_application():
    connection = get_connection()
    adoption_repository = MySqlHistoricalOrderAdoptionRepository(connection)
    adoption_workflow = HistoricalOrderAdoptionWorkflow(
        adoption_repository,
        lambda: HistoricalOrderReviewRemediationMySqlUnitOfWork(connection),
        MySqlHistoricalAssignmentWriter(connection),
        matching_pending_deposit=MySqlHistoricalPendingDepositMatchingRepository(
            connection
        ),
    )
    repository = MySqlHistoricalOrderReviewRemediationRepository(connection, adoption_workflow)
    workflow = HistoricalReviewRemediationWorkflow(
        repository,
        lambda: HistoricalOrderReviewRemediationMySqlUnitOfWork(connection),
    )
    try:
        yield HistoricalOrderReviewRemediationApplication(workflow)
    finally:
        connection.close()


__all__ = [
    "HistoricalOrderReviewRemediationApplication",
    "get_historical_order_review_remediation_application",
]

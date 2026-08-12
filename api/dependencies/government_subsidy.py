"""Per-request construction for the Government Subsidy application."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.government_subsidy.ledger_workflow import (
    GovernmentSubsidyLedgerWorkflow,
    GovernmentSubsidyWorkflowRepository,
)
from subsystems.government_subsidy.claim_workflow import (
    GovernmentSubsidyClaimRepository,
    GovernmentSubsidyClaimWorkflow,
)
from subsystems.government_subsidy.overpayment_workflow import GovernmentSubsidyOverpaymentWorkflow


@dataclass(slots=True)
class GovernmentSubsidyApplication:
    repository: (
        GovernmentSubsidyWorkflowRepository
        | GovernmentSubsidyClaimRepository
    )
    ledger_workflow: GovernmentSubsidyLedgerWorkflow
    claim_workflow: GovernmentSubsidyClaimWorkflow
    overpayment_workflow: GovernmentSubsidyOverpaymentWorkflow

    def list_batches(self, cursor, limit):
        return self.claim_workflow.list_batches(cursor, limit)

    def query_batch(self, batch_id):
        return self.claim_workflow.query_batch(batch_id)

    def preview_claim_plan(self, intent):
        return self.claim_workflow.preview_plan(intent)

    def apply_claim_plan(self, request):
        return self.claim_workflow.apply(request)

    def preview_claim_submission(self, intent):
        return self.claim_workflow.preview_submission(intent)

    def apply_claim_submission(self, request):
        return self.claim_workflow.apply(request)

    def preview_claim_approval(self, intent):
        return self.claim_workflow.preview_approval(intent)

    def apply_claim_approval(self, request):
        return self.claim_workflow.apply(request)

    def preview_receipt(self, intent):
        return self.ledger_workflow.preview_receipt(intent)

    def apply_receipt(self, request):
        return self.ledger_workflow.apply_receipt(request)

    def preview_reversal(self, intent):
        return self.ledger_workflow.preview_reversal(intent)

    def apply_reversal(self, request):
        return self.ledger_workflow.apply_reversal(request)

    def preview_receipt_with_overage(self, row_id, batch_id, intents):
        return self.overpayment_workflow.preview_receipt_with_overage(row_id, batch_id, intents)

    def apply_receipt_with_overage(self, request):
        return self.overpayment_workflow.apply_receipt_with_overage(request)

    def preview_overpayment_offset(self, identity, intents):
        return self.overpayment_workflow.preview_offset(identity, intents)

    def apply_overpayment_offset(self, request):
        return self.overpayment_workflow.apply_offset(request)

    def preview_overpayment_return(self, identity, due_date, evidence_reference):
        return self.overpayment_workflow.preview_return(identity, due_date, evidence_reference)

    def apply_overpayment_return(self, request):
        return self.overpayment_workflow.apply_return(request)

    def preview_overpayment_return_reconciliation(self, identity, finance_import_row_id):
        return self.overpayment_workflow.preview_return_reconciliation(identity, finance_import_row_id)

    def apply_overpayment_return_reconciliation(self, request):
        return self.overpayment_workflow.apply_return_reconciliation(request)


def get_government_subsidy_application():
    connection = get_connection()
    try:
        yield build_government_subsidy_application(connection)
    finally:
        connection.close()


def build_government_subsidy_application(connection):
    from infrastructure.mysql.government_subsidy_repository import (
        MySqlGovernmentSubsidyRepository,
    )

    repository = MySqlGovernmentSubsidyRepository(connection)
    ledger_workflow = GovernmentSubsidyLedgerWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
    )
    claim_workflow = GovernmentSubsidyClaimWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
    )
    return GovernmentSubsidyApplication(repository, ledger_workflow, claim_workflow, GovernmentSubsidyOverpaymentWorkflow(repository, lambda: MySqlUnitOfWork(connection)))


__all__ = [
    "GovernmentSubsidyApplication",
    "build_government_subsidy_application",
    "get_government_subsidy_application",
]

"""Initialize completed intake through the canonical bootstrap writer in the Orders UoW."""

from infrastructure.mysql.case_architecture_bootstrap_repository import MySqlCaseArchitectureBootstrapRepository
from subsystems.bootstrap.case_architecture_status import CaseArchitectureBootstrapStatusService
from subsystems.bootstrap.case_architecture_workflow import (
    CaseArchitectureBootstrapWorkflow, CaseArchitectureBootstrapWorkflowError,
    EnsureCaseArchitectureBootstrap,
)
from subsystems.orders.order_intake_terms_bootstrap import (
    OrderIntakeTermsBootstrapError, OrderIntakeTermsBootstrapFacts,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey


class MySqlOrderIntakeArchitectureInitializer:
    def __init__(self, connection):
        self._status = CaseArchitectureBootstrapStatusService(connection)
        self._workflow = CaseArchitectureBootstrapWorkflow(
            MySqlCaseArchitectureBootstrapRepository(connection), self._no_nested_transaction,
        )

    @staticmethod
    def _no_nested_transaction():
        raise RuntimeError('intake initialization must use the existing Orders transaction')

    def ensure(self, facts: OrderIntakeTermsBootstrapFacts, actor: str, reason: str, key: str) -> None:
        status = self._status.query(facts.case_no)
        if status.ready:
            return  # Existing amounts, versions and policy snapshots remain untouched.
        if status.domain_blockers or status.recommendation is None:
            raise OrderIntakeTermsBootstrapError('order_intake_initialization_blocked',
                blockers=status.domain_blockers or ('case_architecture_bootstrap_recommendation_unavailable',))
        identity = 'intake-bootstrap:' + fingerprint_payload({'case_no': facts.case_no, 'key': key}).value
        correlation = CorrelationId(identity)
        try:
            preview = self._workflow.preview(status.recommendation, correlation)
            self._workflow.ensure_in_unit_of_work(EnsureCaseArchitectureBootstrap(
                intent=status.recommendation,
                expected_order_version=ExpectedVersion(facts.lifecycle_version),
                preview_fingerprint=preview.fingerprint,
                idempotency_key=IdempotencyKey(identity),
                actor=ActorContext(actor.strip()), reason=reason.strip(), correlation_id=correlation,
            ))
        except CaseArchitectureBootstrapWorkflowError as error:
            raise OrderIntakeTermsBootstrapError('order_intake_initialization_blocked',
                blockers=error.error.domain_blockers or (error.error.code,)) from error

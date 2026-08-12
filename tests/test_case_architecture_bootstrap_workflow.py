from datetime import date

from domains.bootstrap.case_architecture import (
    BootstrapPresence,
    CaseArchitectureBootstrapFacts,
    CaseArchitectureBootstrapIntent,
    CaseRootFacts,
    ClientPaymentTermsRootFacts,
    PayrollPolicyKind,
    RatePolicyFacts,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.bootstrap.case_architecture_workflow import (
    CaseArchitectureBootstrapWorkflow,
    CommandClaimState,
    EnsureCaseArchitectureBootstrap,
)


class BootstrapWorkflowRepository:
    def __init__(self, facts):
        self.facts = facts
        self.created_candidates = []
        self.existing_event_lookups = []
        self.saved_receipt = None

    def load_for_preview(self, _intent):
        return self.facts

    def load_for_ensure(self, _intent):
        return self.facts

    def claim_command(self, _command, _fingerprint):
        return CommandClaimState.CREATED

    def find_receipt(self, _key, *, for_update):
        assert for_update is True
        return None

    def create_bootstrap(self, _command, candidate):
        self.created_candidates.append(candidate)
        return 71

    def existing_bootstrap_event_id(self, case_no):
        self.existing_event_lookups.append(case_no)
        return 72

    def save_receipt(self, _key, stored):
        self.saved_receipt = stored


class RecordingUnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def commit(self):
        self.committed = True


def test_ensure_creates_missing_bootstrap_roots_while_adopting_existing_scheduling():
    facts = CaseArchitectureBootstrapFacts(
        order=CaseRootFacts("115000028", 0, date(2026, 12, 12), 20, 24, "非市民"),
        payroll_rate_policy=RatePolicyFacts(
            "approved-rates-v1", PayrollPolicyKind.NON_CITIZEN, MoneyNTD(320), date(2020, 1, 1), None
        ),
        presence=BootstrapPresence(scheduling_aggregate=True, scheduling_version=1, scheduling_generation=1),
    )
    repository = BootstrapWorkflowRepository(facts)
    unit_of_work = RecordingUnitOfWork()
    workflow = CaseArchitectureBootstrapWorkflow(repository, lambda: unit_of_work)
    intent = CaseArchitectureBootstrapIntent(
        "115000028",
        ClientPaymentTermsRootFacts("client-approved-v1", MoneyNTD(320), 5, date(2026, 6, 15), date(2026, 12, 12)),
        "approved-rates-v1",
    )
    preview = workflow.preview(intent, CorrelationId("bootstrap-preview"))

    receipt = workflow.ensure(
        EnsureCaseArchitectureBootstrap(
            intent, ExpectedVersion(0), preview.fingerprint, IdempotencyKey("bootstrap-adopt-1"),
            ActorContext("test-admin"), "adopt existing scheduling", CorrelationId("bootstrap-apply"),
        )
    )

    assert receipt.bootstrap_event_id == 71
    assert receipt.bootstrap_created is True
    assert receipt.scheduling_version == 1
    assert receipt.scheduling_generation == 1
    assert len(repository.created_candidates) == 1
    assert repository.existing_event_lookups == []
    assert repository.saved_receipt is not None
    assert unit_of_work.committed is True

from __future__ import annotations

from domains.government_subsidy.claims import (
    ClaimPlanningFacts,
    ClaimPlanningIntent,
    ClaimPlanningSourceItem,
)
from domains.government_subsidy.ledger import (
    ClaimBatchFacts,
    ClaimBatchIdentity,
    ClaimItemSnapshot,
    OfficialAssignmentServiceFacts,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.government_subsidy.claim_workflow import (
    ClaimPlanningApplyRequest,
    GovernmentSubsidyClaimState,
    GovernmentSubsidyClaimWorkflow,
)


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _Repository:
    def __init__(self):
        self.receipt = None
        self.writes = []

    def load_claim_planning_facts(self, intent, *, lock):
        del lock
        assignment = OfficialAssignmentServiceFacts(1, "CASE-1", 7, 2, 8, True)
        source = ClaimPlanningSourceItem(assignment, MoneyNTD(350))
        return ClaimPlanningFacts(intent, (source,))

    def load_batch(self, *_args, **_kwargs):
        item = ClaimItemSnapshot(1, 5, 1, "CASE-1", 7, 16, MoneyNTD(350), MoneyNTD(5600), MoneyNTD(0), MoneyNTD(0))
        return ClaimBatchFacts(5, ClaimBatchIdentity(2026, 3, 1), 0, False, False, (item,))

    def list_batches(self, *_):
        raise AssertionError("not used")

    def claim_command(self, *_):
        return GovernmentSubsidyClaimState.CREATED if self.receipt is None else GovernmentSubsidyClaimState.MATCHED

    def find_claim_receipt(self, *_args, **_kwargs):
        return self.receipt

    def create_claim_batch(self, _request, _candidate):
        self.writes.append("batch")
        return 5

    def append_claim_submission(self, *_):
        self.writes.append("submission")

    def append_claim_approval(self, *_):
        self.writes.append("approval")

    def append_claim_outbox(self, *_):
        self.writes.append("outbox")

    def save_claim_receipt(self, command):
        self.writes.append("receipt")
        self.receipt = command.stored_receipt


def _workflow(repository):
    return GovernmentSubsidyClaimWorkflow(repository, _UnitOfWork)


def _request(preview):
    return ClaimPlanningApplyRequest(
        ClaimPlanningIntent(ClaimBatchIdentity(2026, 3, 1)),
        ExpectedVersion(0), preview.fingerprint, IdempotencyKey("gov-claim-1"),
        ActorContext("admin"), "create claim batch", CorrelationId("gov-claim-corr"),
    )


def test_claim_plan_apply_persists_canonical_batch_outbox_and_receipt():
    repository = _Repository()
    workflow = _workflow(repository)
    preview = workflow.preview_plan(ClaimPlanningIntent(ClaimBatchIdentity(2026, 3, 1)))

    receipt = workflow.apply(_request(preview))

    assert receipt.batch_id == 5
    assert receipt.status == "draft"
    assert receipt.total_ntd == 5600
    assert repository.writes == ["batch", "outbox", "receipt"]


def test_claim_plan_apply_replays_matching_idempotent_receipt_without_writes():
    repository = _Repository()
    workflow = _workflow(repository)
    preview = workflow.preview_plan(ClaimPlanningIntent(ClaimBatchIdentity(2026, 3, 1)))
    request = _request(preview)

    first = workflow.apply(request)
    second = workflow.apply(request)

    assert second == first
    assert repository.writes == ["batch", "outbox", "receipt"]

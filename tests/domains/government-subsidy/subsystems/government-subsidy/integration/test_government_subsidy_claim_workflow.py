from __future__ import annotations

import pytest

from domains.government_subsidy.claims import (
    ClaimPlanningFacts,
    ClaimPlanningIntent,
    ClaimPlanningSourceItem,
    build_claim_planning_candidate,
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


def test_claim_plan_calculates_frozen_450_rate_for_40_official_hours():
    assignment = OfficialAssignmentServiceFacts(1, "CASE-450", 7, 5, 8, True)
    source = ClaimPlanningSourceItem(assignment, MoneyNTD(450))

    candidate = build_claim_planning_candidate(
        ClaimPlanningFacts(
            ClaimPlanningIntent(ClaimBatchIdentity(2026, 3, 1)),
            (source,),
        )
    )

    assert candidate.items[0].claimed_hours == 40
    assert candidate.items[0].unit_price_ntd == MoneyNTD(450)
    assert candidate.items[0].requested_amount_ntd == MoneyNTD(18000)
    assert candidate.requested_total_ntd == MoneyNTD(18000)


@pytest.mark.parametrize(("hours_per_day", "days", "rate", "expected"), [
    (8, 5, 450, 18000),
    (8.0, 5, 450, 18000),
    (7.5, 3, 350, 7875),
    (0.5, 1, 450, 225),
])
def test_claim_plan_accepts_integral_and_half_hour_service_facts(hours_per_day, days, rate, expected):
    assignment = OfficialAssignmentServiceFacts(1, "CASE-HALF", 7, days, hours_per_day, True)
    candidate = build_claim_planning_candidate(ClaimPlanningFacts(
        ClaimPlanningIntent(ClaimBatchIdentity(2026, 3, 1)),
        (ClaimPlanningSourceItem(assignment, MoneyNTD(rate)),),
    ))
    assert candidate.items[0].claimed_hours == days * hours_per_day
    assert candidate.items[0].requested_amount_ntd == MoneyNTD(expected)
    assert candidate.requested_total_ntd == MoneyNTD(expected)


def test_claim_plan_rejects_fractional_ntd_without_rounding():
    assignment = OfficialAssignmentServiceFacts(1, "CASE-FRACTION", 7, 1, 0.5, True)
    with pytest.raises(ValueError, match="whole NTD"):
        build_claim_planning_candidate(ClaimPlanningFacts(
            ClaimPlanningIntent(ClaimBatchIdentity(2026, 3, 1)),
            (ClaimPlanningSourceItem(assignment, MoneyNTD(351)),),
        ))

"""
File: test_service_before_replacement_workflow.py
Description: 驗證 Scheduling 服務前換人的交易、重播與安全停止。
"""

from dataclasses import replace
from datetime import date

import pytest

from domains.scheduling.service_before_replacement import (
    ActualServiceProof,
    ReplacementRootIdentity,
    ReplacementRootKind,
    ReplacementResumeStep,
    ReplacementScenario,
    ServiceBeforeReplacementFacts,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.scheduling.service_before_replacement_workflow import (
    ApplyServiceBeforeReplacement,
    ReplacementApplyStatus,
    ReplacementOwnerReadback,
    ServiceBeforeReplacementQueryRequest,
    ServiceBeforeReplacementWorkflow,
    ServiceBeforeReplacementWorkflowError,
    StoredReplacementReceipt,
    replacement_command_fingerprint,
)


CASE = "CASE-WORKFLOW-1"


class FakeUnitOfWork:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeRepository:
    def __init__(self, facts):
        self.facts = facts
        self.readback = None
        self.stored = None
        self.persisted = []
        self.load_modes = []
        self.fail_persist = False
        self.fail_readback = False
        self.fail_post_commit_readback = False
        self.corrupt_post_commit_root_ids = None
        self.return_mismatched_facts = False

    def load_facts(self, case_no, *, for_update):
        self.load_modes.append((case_no, for_update))
        return self.facts if case_no == self.facts.case_no or self.return_mismatched_facts else None

    def find_receipt(self, key, case_no, *, for_update):
        return self.stored if case_no == CASE else None

    def persist_replacement(self, bundle):
        if self.fail_persist:
            raise RuntimeError("persist failed")
        self.persisted.append(bundle)
        candidate = bundle.candidate
        self.stored = StoredReplacementReceipt(
            bundle.receipt.command_fingerprint,
            bundle.receipt,
        )
        self.readback = ReplacementOwnerReadback(
            candidate.case_no,
            candidate.replacement_generation_identity,
            candidate.replacement_event_identity,
            candidate.successor_round_identity,
            candidate.resulting_generation_version,
            candidate.resulting_event_version,
            candidate.resulting_aggregate_version,
            candidate.retained_root_ids,
            candidate.superseded_root_ids,
            candidate.created_root_ids,
            candidate.resume_step,
            0 if candidate.candidate_pool_reuse_proof is None else 1,
            (
                "blocked_no_candidate"
                if candidate.scenario is ReplacementScenario.R07
                else None
            ),
        )

    def load_owner_readback(self, case_no, *, for_update):
        if self.fail_readback or (self.fail_post_commit_readback and not for_update):
            return None
        if self.corrupt_post_commit_root_ids and not for_update:
            return replace(self.readback, **{self.corrupt_post_commit_root_ids: ("successor-round:wrong",)})
        return self.readback


def facts(*, case_no=CASE, service_dates=()):
    roots = tuple(
        ReplacementRootIdentity(kind, f"{kind.value}:old", case_no)
        for kind in (
            ReplacementRootKind.MATCHING_PLAN,
            ReplacementRootKind.MATCHING_SEGMENT,
            ReplacementRootKind.MATCHING_REPLY,
            ReplacementRootKind.RECIPIENT_CONFIRMATION,
        )
    )
    proof = ActualServiceProof(case_no, tuple(service_dates), "official-service:1", 13)
    return ServiceBeforeReplacementFacts(
        case_no, ReplacementScenario.R02, tuple(service_dates), "generation:old", "event:old", 8, 13,
        roots, actual_service_proof_available=True, actual_service_proof=proof,
        aggregate_version=8, prior_aggregate_identity="aggregate:old", replacement_reason="replace",
        reason_evidence=("note:1",),
    )


def make_workflow(repository):
    uow = FakeUnitOfWork()
    return ServiceBeforeReplacementWorkflow(repository, lambda: uow), uow


def request(candidate, *, key="key:1", reason="replace", evidence=("note:1",)):
    current = facts()
    return ApplyServiceBeforeReplacement(
        CASE, ReplacementScenario.R02, ExpectedVersion(current.generation_version),
        ExpectedVersion(current.event_version), ExpectedVersion(current.aggregate_version),
        current.prior_generation_identity, current.prior_event_identity, current.prior_aggregate_identity,
        candidate.fingerprint, IdempotencyKey(key), ActorContext("operator:1", ("scheduling.replace",)),
        reason, evidence, CorrelationId("correlation:1"),
    )


def test_query_and_preview_are_zero_write_and_use_unlocked_reads():
    repository = FakeRepository(facts())
    workflow, _ = make_workflow(repository)
    query_request = ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1"))
    result = workflow.query(query_request)
    candidate = workflow.preview(query_request)
    assert result.case_no == CASE
    assert candidate.can_apply
    assert repository.persisted == []
    assert repository.load_modes == [(CASE, False), (CASE, False)]


@pytest.mark.parametrize("operation", ["query", "preview"])
def test_query_and_preview_reject_repository_case_identity_mismatch(operation):
    repository = FakeRepository(facts(case_no="CASE-OTHER"))
    repository.return_mismatched_facts = True
    workflow, _ = make_workflow(repository)
    request_ = ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1"))

    with pytest.raises(ServiceBeforeReplacementWorkflowError) as error:
        getattr(workflow, operation)(request_)

    assert error.value.error.code == "replacement_case_identity_mismatch"


def test_apply_persists_one_bundle_and_fresh_readback_proves_applied():
    repository = FakeRepository(facts())
    workflow, uow = make_workflow(repository)
    preview = workflow.preview(ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1")))
    result = workflow.apply(request(preview))
    assert result.status is ReplacementApplyStatus.APPLIED
    assert result.receipt is not None
    assert len(repository.persisted) == 1
    assert repository.persisted[0].outbox.intent_type == "service_before_replacement_successor_created"
    assert uow.commits == 1


def test_same_key_same_payload_replays_and_different_payload_conflicts():
    repository = FakeRepository(facts())
    workflow, uow = make_workflow(repository)
    preview = workflow.preview(ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1")))
    first = workflow.apply(request(preview))
    replay = workflow.apply(request(preview))
    assert first.status is ReplacementApplyStatus.APPLIED
    assert replay.status is ReplacementApplyStatus.REPLAYED
    assert replay.receipt == first.receipt
    assert len(repository.persisted) == 1
    assert uow.commits == 2
    with pytest.raises(ServiceBeforeReplacementWorkflowError) as error:
        workflow.apply(request(preview, reason="different"))
    assert error.value.error.code == "replacement_idempotency_conflict"


@pytest.mark.parametrize("service_dates, expected", [((date(2026, 8, 28),), ReplacementApplyStatus.SUBSTITUTION_REFERRAL)])
def test_actual_service_is_referral_and_blocked_candidate_is_zero_write(service_dates, expected):
    repository = FakeRepository(facts(service_dates=service_dates))
    workflow, uow = make_workflow(repository)
    preview_request = ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1"))
    preview = workflow.preview(preview_request)
    result = workflow.apply(request(preview))
    assert result.status is expected
    assert repository.persisted == []
    assert uow.commits == 0


def test_stale_apply_is_rejected_after_fresh_lock():
    repository = FakeRepository(facts())
    workflow, _ = make_workflow(repository)
    preview_request = ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1"))
    preview = workflow.preview(preview_request)
    changed = facts()
    repository.facts = ServiceBeforeReplacementFacts(
        changed.case_no, changed.scenario, changed.actual_service_dates, changed.prior_generation_identity,
        changed.prior_event_identity, 9, changed.event_version, changed.current_roots,
        actual_service_proof_available=True, actual_service_proof=changed.actual_service_proof,
        aggregate_version=9, prior_aggregate_identity="aggregate:new", replacement_reason="replace",
        reason_evidence=("note:1",),
    )
    with pytest.raises(ServiceBeforeReplacementWorkflowError) as error:
        workflow.apply(request(preview))
    assert error.value.error.code == "replacement_stale_version"
    assert repository.persisted == []


def test_persistence_failure_rolls_back_and_does_not_claim_success():
    repository = FakeRepository(facts())
    repository.fail_persist = True
    workflow, uow = make_workflow(repository)
    preview = workflow.preview(ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1")))
    result = workflow.apply(request(preview))
    assert result.status is ReplacementApplyStatus.OUTCOME_UNKNOWN
    assert uow.rollbacks == 1
    assert result.receipt is None


def test_post_commit_readback_failure_is_typed_unknown_not_receipt_only_success():
    repository = FakeRepository(facts())
    repository.fail_post_commit_readback = True
    workflow, uow = make_workflow(repository)
    preview = workflow.preview(ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1")))
    result = workflow.apply(request(preview))
    assert result.status is ReplacementApplyStatus.OUTCOME_UNKNOWN
    assert result.receipt is not None
    assert result.readback is None
    assert uow.commits == 1
    assert uow.rollbacks == 0


def test_post_commit_readback_requires_exact_created_root_ids():
    repository = FakeRepository(facts())
    repository.corrupt_post_commit_root_ids = "created_root_ids"
    workflow, uow = make_workflow(repository)
    preview = workflow.preview(ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1")))

    result = workflow.apply(request(preview))

    assert result.status is ReplacementApplyStatus.OUTCOME_UNKNOWN
    assert result.receipt is not None
    assert result.readback is not None
    assert uow.commits == 1
    assert uow.rollbacks == 0


def test_apply_rejects_repository_case_identity_mismatch():
    repository = FakeRepository(facts())
    workflow, uow = make_workflow(repository)
    preview = workflow.preview(ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1")))
    repository.facts = facts(case_no="CASE-OTHER")
    repository.return_mismatched_facts = True

    with pytest.raises(ServiceBeforeReplacementWorkflowError) as error:
        workflow.apply(request(preview))

    assert error.value.error.code == "replacement_case_identity_mismatch"
    assert repository.persisted == []
    assert uow.rollbacks == 1


def test_replay_requires_readback_identity_to_match_receipt():
    repository = FakeRepository(facts())
    workflow, _ = make_workflow(repository)
    preview = workflow.preview(ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1")))
    first = workflow.apply(request(preview))
    repository.readback = ReplacementOwnerReadback(
        CASE, "replacement-generation:wrong", first.receipt.replacement_event_identity,
        first.receipt.successor_round_identity, first.receipt.resulting_generation_version,
        first.receipt.resulting_event_version, first.receipt.resulting_aggregate_version, (),
        preview.superseded_root_ids, preview.created_root_ids,
        ReplacementResumeStep.STEP_4, 1, None,
    )
    replay = workflow.apply(request(preview))
    assert replay.status is ReplacementApplyStatus.OUTCOME_UNKNOWN
    assert replay.error.code == "replacement_replay_readback_unknown"


@pytest.mark.parametrize("root_field", ["retained_root_ids", "superseded_root_ids", "created_root_ids"])
def test_replay_requires_exact_root_ids(root_field):
    repository = FakeRepository(facts())
    workflow, _ = make_workflow(repository)
    preview = workflow.preview(ServiceBeforeReplacementQueryRequest(CASE, ReplacementScenario.R02, CorrelationId("correlation:1")))
    first = workflow.apply(request(preview))
    assert first.status is ReplacementApplyStatus.APPLIED

    repository.corrupt_post_commit_root_ids = root_field
    replay = workflow.apply(request(preview))

    assert replay.status is ReplacementApplyStatus.OUTCOME_UNKNOWN
    assert replay.error.code == "replacement_replay_readback_unknown"

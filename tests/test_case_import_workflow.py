"""Contract tests for the canonical Case Import transaction workflow."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.case_import.case_import_workflow import (
    ApplyCaseImport,
    CaseImportClaimState,
    CaseImportReceipt,
    CaseImportWorkflow,
    CaseImportWorkflowError,
    StoredCaseImportReceipt,
)
from subsystems.case_import.beclass_import_review_workflow import (
    ApplyBeClassImportReview,
    BeClassImportReviewClaimState,
    BeClassImportReviewWorkflow,
    BeClassImportReviewWorkflowError,
    BeClassImportReviewWriteReceipt,
)
from subsystems.bootstrap.case_architecture_workflow import (
    CaseArchitectureBootstrapWorkflow,
    CaseArchitectureBootstrapWorkflowError,
    CommandClaimState,
    EnsureCaseArchitectureBootstrap,
)


@dataclass
class FakeUnitOfWork:
    committed: bool = False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return None

    def commit(self):
        self.committed = True


class FakeRepository:
    def __init__(self, candidate):
        self.candidate = candidate
        self.facts = SimpleNamespace(case_exists=False)
        self.claim = CaseImportClaimState.CREATED
        self.stored = None
        self.saved = None
        self.consumed = None

    def load(self, intent, *, for_update):
        return self.facts

    def claim_command(self, command, command_fingerprint):
        return self.claim

    def find_receipt(self, key):
        return self.stored

    def insert_case_roots(self, candidate):
        return 12

    def create_architecture_bootstrap(self, command, candidate):
        return 34

    def append_import_event(self, command, candidate, client_id, bootstrap_event_id):
        return 56

    def consume_provisional_registration(self, command, candidate, client_id, import_event_id):
        self.consumed = (candidate.provisional_registration.registration_id, client_id, import_event_id)
        return 78

    def save_receipt(self, key, stored):
        self.saved = stored


def test_apply_persists_once_then_replays_without_second_commit(monkeypatch):
    candidate = _candidate("case-001")
    repository = FakeRepository(candidate)
    unit_of_work = FakeUnitOfWork()
    monkeypatch.setattr(
        "subsystems.case_import.case_import_workflow.build_case_import_candidate",
        lambda facts, intent: candidate,
    )
    workflow = CaseImportWorkflow(repository, lambda: unit_of_work)
    command = _command(candidate)

    first = workflow.apply(command)
    repository.claim = CaseImportClaimState.MATCHED
    repository.stored = repository.saved
    second = workflow.apply(command)

    assert first == second
    assert unit_of_work.committed is True


def test_apply_rejects_claim_without_receipt(monkeypatch):
    candidate = _candidate("case-002")
    repository = FakeRepository(candidate)
    repository.claim = CaseImportClaimState.MATCHED
    monkeypatch.setattr(
        "subsystems.case_import.case_import_workflow.build_case_import_candidate",
        lambda facts, intent: candidate,
    )
    workflow = CaseImportWorkflow(repository, FakeUnitOfWork)

    with pytest.raises(CaseImportWorkflowError, match="idempotency_evidence_incomplete"):
        workflow.apply(_command(candidate))


def test_apply_rejects_changed_case_existence(monkeypatch):
    candidate = _candidate("case-003")
    repository = FakeRepository(candidate)
    repository.facts = SimpleNamespace(case_exists=True)
    monkeypatch.setattr(
        "subsystems.case_import.case_import_workflow.build_case_import_candidate",
        lambda facts, intent: candidate,
    )
    workflow = CaseImportWorkflow(repository, FakeUnitOfWork)

    with pytest.raises(CaseImportWorkflowError, match="case_import_candidate_stale"):
        workflow.apply(_command(candidate))


def test_apply_consumes_selected_provisional_registration(monkeypatch):
    candidate = _candidate("case-004")
    candidate.provisional_registration = SimpleNamespace(registration_id=91)
    repository = FakeRepository(candidate)
    monkeypatch.setattr(
        "subsystems.case_import.case_import_workflow.build_case_import_candidate",
        lambda facts, intent: candidate,
    )

    receipt = CaseImportWorkflow(repository, FakeUnitOfWork).apply(_command(candidate))

    assert repository.consumed == (91, 12, 56)
    assert receipt.provisional_registration_id == 91
    assert receipt.provisional_case_issue_event_id == 78


def _candidate(case_no):
    fingerprint = fingerprint_payload({"case_no": case_no})
    return SimpleNamespace(
        case_no=case_no,
        fingerprint=fingerprint,
        source_fingerprint=PreviewFingerprint("a" * 64),
    )


def _command(candidate):
    preview_fingerprint = fingerprint_payload(
        {"import_version": 0, "candidate_fingerprint": candidate.fingerprint.value}
    )
    return ApplyCaseImport(
        SimpleNamespace(case_no=candidate.case_no, provisional_registration_id=None),
        ExpectedVersion(0),
        preview_fingerprint,
        IdempotencyKey(f"key-{candidate.case_no}"),
        ActorContext("case-import-test"),
        "import case",
        CorrelationId(f"correlation-{candidate.case_no}"),
    )


class FakeBeClassRepository:
    def __init__(self, candidate):
        self.candidate = candidate
        self.facts = SimpleNamespace(review_version=0)
        self.claim = BeClassImportReviewClaimState.CREATED
        self.stored = None
        self.saved = None

    def load(self, review_identity, *, for_update):
        return self.facts

    def claim_command(self, command, command_fingerprint):
        return self.claim

    def find_receipt(self, key):
        return self.stored

    def append_resolution_event(self, command, candidate, write_receipt):
        return 78

    def append_outbox(self, candidate, review_event_id):
        return 90

    def save_receipt(self, key, stored):
        self.saved = stored


class FakeBeClassWriter:
    def apply_corrected_row(self, candidate):
        return BeClassImportReviewWriteReceipt("client-321")


def test_beclass_apply_persists_then_replays(monkeypatch):
    candidate = SimpleNamespace(
        fingerprint=fingerprint_payload({"review": "review-001"}),
        review_identity="review-001",
        resulting_version=1,
    )
    repository = FakeBeClassRepository(candidate)
    unit_of_work = FakeUnitOfWork()
    monkeypatch.setattr(
        "subsystems.case_import.beclass_import_review_workflow.build_beclass_import_review_candidate",
        lambda facts, intent: candidate,
    )
    monkeypatch.setattr(
        "subsystems.case_import.beclass_import_review_workflow.resolved_anomaly_snapshot",
        lambda candidate: {"active": False},
    )
    workflow = BeClassImportReviewWorkflow(repository, FakeBeClassWriter(), lambda: unit_of_work)
    command = _beclass_command(candidate)

    first = workflow.apply(command)
    repository.claim = BeClassImportReviewClaimState.MATCHED
    repository.stored = repository.saved
    second = workflow.apply(command)

    assert first == second
    assert unit_of_work.committed is True


def test_beclass_apply_rejects_stale_version(monkeypatch):
    candidate = SimpleNamespace(
        fingerprint=fingerprint_payload({"review": "review-002"}),
        review_identity="review-002",
        resulting_version=2,
    )
    repository = FakeBeClassRepository(candidate)
    repository.facts = SimpleNamespace(review_version=1)
    monkeypatch.setattr(
        "subsystems.case_import.beclass_import_review_workflow.build_beclass_import_review_candidate",
        lambda facts, intent: candidate,
    )
    workflow = BeClassImportReviewWorkflow(repository, FakeBeClassWriter(), FakeUnitOfWork)

    with pytest.raises(BeClassImportReviewWorkflowError, match="beclass_import_review_stale"):
        workflow.apply(_beclass_command(candidate))


def _beclass_command(candidate):
    preview_fingerprint = fingerprint_payload(
        {
            "candidate_fingerprint": candidate.fingerprint.value,
            "expected_version": 0,
            "bounded_anomaly_snapshot": {"active": False},
        }
    )
    return ApplyBeClassImportReview(
        SimpleNamespace(review_identity=candidate.review_identity),
        ExpectedVersion(0),
        preview_fingerprint,
        IdempotencyKey(f"beclass-key-{candidate.review_identity}"),
        ActorContext("beclass-review-test"),
        "resolve import row",
        CorrelationId(f"beclass-correlation-{candidate.review_identity}"),
    )


class FakeBootstrapRepository:
    def __init__(self, candidate):
        self.candidate = candidate
        self.facts = SimpleNamespace(order=SimpleNamespace(order_version=0))
        self.claim = CommandClaimState.CREATED
        self.stored = None
        self.saved = None

    def load_for_preview(self, intent):
        return self.facts

    def load_for_ensure(self, intent):
        return self.facts

    def claim_command(self, command, command_fingerprint):
        return self.claim

    def find_receipt(self, key, *, for_update):
        return self.stored

    def create_bootstrap(self, command, candidate):
        return 41

    def existing_bootstrap_event_id(self, case_no):
        return 42

    def save_receipt(self, key, stored):
        self.saved = stored


def test_bootstrap_ensure_persists_then_replays(monkeypatch):
    from domains.bootstrap.case_architecture import BootstrapMutation

    candidate = SimpleNamespace(
        case_no="case-bootstrap-001",
        order_version=0,
        scheduling_version=0,
        scheduling_generation=0,
        mutation=BootstrapMutation.CREATE,
        fingerprint=fingerprint_payload({"bootstrap": "case-bootstrap-001"}),
    )
    repository = FakeBootstrapRepository(candidate)
    unit_of_work = FakeUnitOfWork()
    monkeypatch.setattr(
        "subsystems.bootstrap.case_architecture_workflow.build_case_architecture_bootstrap_candidate",
        lambda facts, intent: candidate,
    )
    workflow = CaseArchitectureBootstrapWorkflow(repository, lambda: unit_of_work)
    command = _bootstrap_command(candidate)

    first = workflow.ensure(command)
    repository.claim = CommandClaimState.MATCHED
    repository.stored = repository.saved
    second = workflow.ensure(command)

    assert first == second
    assert unit_of_work.committed is True


def test_bootstrap_ensure_rejects_stale_order_version(monkeypatch):
    from domains.bootstrap.case_architecture import BootstrapMutation

    candidate = SimpleNamespace(
        case_no="case-bootstrap-002",
        order_version=1,
        scheduling_version=0,
        scheduling_generation=0,
        mutation=BootstrapMutation.CREATE,
        fingerprint=fingerprint_payload({"bootstrap": "case-bootstrap-002"}),
    )
    repository = FakeBootstrapRepository(candidate)
    repository.facts = SimpleNamespace(order=SimpleNamespace(order_version=1))
    monkeypatch.setattr(
        "subsystems.bootstrap.case_architecture_workflow.build_case_architecture_bootstrap_candidate",
        lambda facts, intent: candidate,
    )
    workflow = CaseArchitectureBootstrapWorkflow(repository, FakeUnitOfWork)

    with pytest.raises(CaseArchitectureBootstrapWorkflowError, match="case_architecture_bootstrap_stale"):
        workflow.ensure(_bootstrap_command(candidate))


def _bootstrap_command(candidate):
    return EnsureCaseArchitectureBootstrap(
        SimpleNamespace(
            case_no=candidate.case_no,
            client_payment_terms=SimpleNamespace(policy_version="client-v1"),
            payroll_policy_version="payroll-v1",
        ),
        ExpectedVersion(0),
        candidate.fingerprint,
        IdempotencyKey(f"bootstrap-key-{candidate.case_no}"),
        ActorContext("bootstrap-test"),
        "bootstrap case architecture",
        CorrelationId(f"bootstrap-correlation-{candidate.case_no}"),
    )

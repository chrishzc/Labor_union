"""Focused Task 97 boundary tests for the current-only anomaly slice."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pytest

from domains.anomalies.current_issue import (
    CurrentIssueCandidate,
    CurrentIssueProjection,
    OwnerSnapshot,
    RecheckIntent,
    RecheckScope,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.current_issue_recheck import (
    CurrentIssueApplication,
    CurrentIssueRecheckBlocked,
)


NOW = datetime(2026, 8, 29, 1, 0, tzinfo=timezone.utc)


def _scope() -> RecheckScope:
    return RecheckScope("scheduling", "assignment", "assignment", ("a-1",), ("scheduling:assignment:a-1",))


def _candidate(key: str = "ci-a-1") -> CurrentIssueCandidate:
    return CurrentIssueCandidate(key, "SCHEDULE-006", "scheduling", "assignment", "assignment", "a-1", 3, "blocking", True, {"code": "SCHEDULE-006"})


def _intent() -> RecheckIntent:
    return RecheckIntent("recheck:a-1", _scope(), 3, fingerprint_payload({"subject": "a-1"}))


class _Uow:
    def __init__(self, log):
        self.log = log
        self.active = False
        self.committed = False

    def __enter__(self):
        self.active = True
        self.log.append("begin")
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.active = False
        if exception_type is not None or not self.committed:
            self.log.append("rollback")
        return False

    def commit(self):
        self.committed = True
        self.log.append("commit")

    def rollback(self):
        self.log.append("rollback")


class _Repository:
    def __init__(self, snapshot, current=()):
        self.snapshot = snapshot
        self.current = list(current)
        self.events = []
        self.completed = []
        self.intents = []

    def lock_scope(self, scope):
        self.events.append(("lock", scope))

    def read_owner_snapshot(self, scope):
        assert scope == self.snapshot.scope
        return self.snapshot

    def assert_snapshot_current(self, scope, snapshot_token):
        assert scope == self.snapshot.scope
        assert snapshot_token == self.snapshot.snapshot_token

    def list_current(self, scope):
        assert scope == self.snapshot.scope
        return tuple(self.current)

    def upsert_current(self, candidate, verified_at):
        self.events.append(("upsert", candidate.issue_key, verified_at))
        self.current = [item for item in self.current if item.issue_key != candidate.issue_key]
        self.current.append(CurrentIssueProjection(candidate, verified_at, verified_at))

    def delete_current(self, issue_key):
        self.events.append(("delete", issue_key))
        self.current = [item for item in self.current if item.issue_key != issue_key]

    def append_recheck_intent(self, intent):
        self.events.append(("append_intent", intent.intent_identity))
        if intent.intent_identity not in self.intents:
            self.intents.append(intent.intent_identity)

    def complete_recheck_intent(self, intent):
        self.events.append(("complete_intent", intent.intent_identity))
        self.completed.append(intent.intent_identity)


def test_reconcile_deletes_absent_issue_and_completes_intent_in_one_application_uow():
    scope = _scope()
    stale = _candidate("ci-stale")
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object()), (CurrentIssueProjection(stale, NOW, NOW),))
    tx_log = []
    application = CurrentIssueApplication(repository, lambda: _Uow(tx_log), clock=lambda: NOW)

    result = application.reconcile(scope, lambda _snapshot: (_candidate(),), completed_intent=_intent())

    assert result.present_issue_keys == ("ci-a-1",)
    assert result.deleted_issue_keys == ("ci-stale",)
    assert [item.issue_key for item in repository.current] == ["ci-a-1"]
    assert repository.completed == ["recheck:a-1"]
    assert tx_log == ["begin", "commit"]
    assert repository.events[-2:] == [("delete", "ci-stale"), ("complete_intent", "recheck:a-1")]


def test_incomplete_owner_snapshot_performs_no_projection_mutation():
    scope = _scope()
    existing = _candidate()
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object(), authoritative_complete=False), (CurrentIssueProjection(existing, NOW, NOW),))
    application = CurrentIssueApplication(repository, lambda: _Uow([]), clock=lambda: NOW)

    with pytest.raises(CurrentIssueRecheckBlocked, match="incomplete"):
        application.reconcile(scope, lambda _snapshot: ())

    assert [item.issue_key for item in repository.current] == ["ci-a-1"]
    assert not any(event[0] in {"upsert", "delete", "complete_intent"} for event in repository.events)


def test_owner_mutation_and_intent_append_share_commit_boundary():
    scope = _scope()
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object()))
    tx_log = []
    application = CurrentIssueApplication(repository, lambda: _Uow(tx_log))

    result = application.mutate_owner_with_recheck_intent(lambda: "owner-receipt", _intent())

    assert result == "owner-receipt"
    assert repository.intents == ["recheck:a-1"]
    assert tx_log == ["begin", "commit"]


def test_projection_and_intent_completion_rollback_together():
    scope = _scope()
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object()))

    def fail_completion(_intent):
        raise RuntimeError("intent_completion_failed")

    repository.complete_recheck_intent = fail_completion
    tx_log = []
    application = CurrentIssueApplication(repository, lambda: _Uow(tx_log), clock=lambda: NOW)

    with pytest.raises(RuntimeError, match="intent_completion_failed"):
        application.reconcile(scope, lambda _snapshot: (_candidate(),), completed_intent=_intent())

    assert tx_log == ["begin", "rollback"]


def test_generic_durable_job_remains_the_only_claim_lease_retry_mechanism():
    worker_source = Path("subsystems/jobs/durable_job_worker.py").read_text(encoding="utf-8")
    current_source = Path("subsystems/anomalies/current_issue_recheck.py").read_text(encoding="utf-8")

    assert "claim_next" in worker_source
    assert "claim_next" not in current_source
    assert "provider" not in current_source.lower()

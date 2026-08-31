"""Focused Task 97 boundary tests for the current-only anomaly slice."""

# Canonical anomaly-registry root retains this durable current-contract oracle.

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
from shared_kernel.durable_job_queue import DurableJobCommand, DurableJobLease
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.current_issue_recheck import (
    CurrentIssueApplication,
    CurrentIssueRecheckBlocked,
)
from subsystems.jobs.durable_job_worker import DurableJobWorker


NOW = datetime(2026, 8, 29, 1, 0, tzinfo=timezone.utc)


def _scope() -> RecheckScope:
    return RecheckScope("line", "notification_failure", "recipient_unavailable", ("CASE-1",), ("line:notification_failure:CASE-1",))


def _candidate(key: str = "ci_" + "a" * 64) -> CurrentIssueCandidate:
    return CurrentIssueCandidate(
        key,
        "LINE-006",
        "line",
        "notification_failure",
        "recipient_unavailable",
        "CASE-1",
        3,
        "blocking",
        True,
        {"notification_reason": "recipient_unavailable"},
        {"case_no": "CASE-1", "notification_reason": "recipient_unavailable"},
    )


def _intent() -> RecheckIntent:
    return RecheckIntent("recheck:CASE-1", _scope(), 3, fingerprint_payload({"subject": "CASE-1"}))


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
        if intent.intent_identity not in self.completed:
            self.completed.append(intent.intent_identity)


def test_reconcile_deletes_absent_issue_and_completes_intent_in_one_application_uow():
    scope = _scope()
    stale = _candidate("ci_" + "b" * 64)
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object()), (CurrentIssueProjection(stale, NOW, NOW),))
    tx_log = []
    application = CurrentIssueApplication(repository, lambda: _Uow(tx_log), clock=lambda: NOW)

    result = application.reconcile(scope, lambda _snapshot: (_candidate(),), completed_intent=_intent())

    assert result.present_issue_keys == ("ci_" + "a" * 64,)
    assert result.deleted_issue_keys == ("ci_" + "b" * 64,)
    assert [item.issue_key for item in repository.current] == ["ci_" + "a" * 64]
    assert repository.completed == ["recheck:CASE-1"]
    assert tx_log == ["begin", "commit"]
    assert repository.events[-2:] == [("delete", "ci_" + "b" * 64), ("complete_intent", "recheck:CASE-1")]


def test_incomplete_owner_snapshot_performs_no_projection_mutation():
    scope = _scope()
    existing = _candidate()
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object(), authoritative_complete=False), (CurrentIssueProjection(existing, NOW, NOW),))
    application = CurrentIssueApplication(repository, lambda: _Uow([]), clock=lambda: NOW)

    with pytest.raises(CurrentIssueRecheckBlocked, match="incomplete"):
        application.reconcile(scope, lambda _snapshot: ())

    assert [item.issue_key for item in repository.current] == ["ci_" + "a" * 64]
    assert not any(event[0] in {"upsert", "delete", "complete_intent"} for event in repository.events)


def test_owner_mutation_and_intent_append_share_commit_boundary():
    scope = _scope()
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object()))
    tx_log = []
    application = CurrentIssueApplication(repository, lambda: _Uow(tx_log))

    result = application.mutate_owner_with_recheck_intent(lambda: "owner-receipt", _intent())

    assert result == "owner-receipt"
    assert repository.intents == ["recheck:CASE-1"]
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


def test_owner_mutation_is_not_committed_when_recheck_intent_append_fails():
    scope = _scope()
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object()))
    mutation_calls = []

    def fail_append(_intent):
        repository.events.append(("append_intent_failed",))
        raise RuntimeError("intent_append_failed")

    repository.append_recheck_intent = fail_append
    tx_log = []
    application = CurrentIssueApplication(repository, lambda: _Uow(tx_log))

    with pytest.raises(RuntimeError, match="intent_append_failed"):
        application.mutate_owner_with_recheck_intent(
            lambda: mutation_calls.append("owner_mutated"), _intent()
        )

    assert mutation_calls == ["owner_mutated"]
    assert repository.intents == []
    assert tx_log == ["begin", "rollback"]


def test_reconcile_rejects_intent_for_another_scope_before_projection_writes():
    scope = _scope()
    other_scope = RecheckScope(
        "line", "notification_failure", "recipient_unavailable", ("CASE-2",), ("line:notification_failure:CASE-2",)
    )
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object()))
    application = CurrentIssueApplication(repository, lambda: _Uow([]), clock=lambda: NOW)
    other_intent = RecheckIntent(
        "recheck:CASE-2", other_scope, 3, fingerprint_payload({"subject": "CASE-2"})
    )

    with pytest.raises(CurrentIssueRecheckBlocked, match="scope mismatch"):
        application.reconcile(scope, lambda _snapshot: (_candidate(),), completed_intent=other_intent)

    assert not any(event[0] in {"upsert", "delete", "complete_intent"} for event in repository.events)


def test_reconcile_rejects_intent_newer_than_owner_snapshot_before_projection_writes():
    scope = _scope()
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object()))
    application = CurrentIssueApplication(repository, lambda: _Uow([]), clock=lambda: NOW)
    newer_intent = RecheckIntent(
        "recheck:CASE-1:v4", scope, 4, fingerprint_payload({"subject": "CASE-1", "version": 4})
    )

    with pytest.raises(CurrentIssueRecheckBlocked, match="newer than snapshot"):
        application.reconcile(scope, lambda _snapshot: (_candidate(),), completed_intent=newer_intent)

    assert not any(event[0] in {"upsert", "delete", "complete_intent"} for event in repository.events)


def test_recheck_replay_is_idempotent_for_current_projection_and_intent_completion():
    scope = _scope()
    repository = _Repository(OwnerSnapshot(scope, "owner-v3", 3, object()))
    tx_log = []
    application = CurrentIssueApplication(repository, lambda: _Uow(tx_log), clock=lambda: NOW)

    first = application.reconcile(scope, lambda _snapshot: (_candidate(),), completed_intent=_intent())
    second = application.reconcile(scope, lambda _snapshot: (_candidate(),), completed_intent=_intent())

    assert first == second
    assert [item.issue_key for item in repository.current] == ["ci_" + "a" * 64]
    assert repository.completed == ["recheck:CASE-1"]
    assert tx_log == ["begin", "commit", "begin", "commit"]


def test_generic_worker_claim_and_lease_are_short_transactions_around_provider_call():
    command = DurableJobCommand(
        "job-1", "anomaly-recheck:CASE-1", "anomaly.recheck", 1,
        {"subject": "CASE-1"}, "system:anomaly-recheck", "corr-1",
    )
    lease = DurableJobLease("job-1", "lease-1", command, 1)
    events = []

    class DurableRepository:
        def recover_expired_canonical_leases(self, _delay):
            events.append("recover")
            return 0

        def claim_next_canonical_command(self, _worker_id, _lease_seconds):
            events.append("claim")
            return lease

        def complete_canonical_claim(self, _lease, _outcome):
            events.append("complete")

    class DurableTransaction:
        def begin(self):
            events.append("begin")

        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    def provider_handler(_payload):
        events.append("provider")
        return {}, "recheck-receipt:CASE-1"

    worker = DurableJobWorker(
        DurableRepository(), DurableTransaction(), {"anomaly.recheck": provider_handler}, "worker-1"
    )
    assert worker.recover_and_run_once() is True

    assert events == [
        "begin", "recover", "commit",
        "begin", "claim", "commit",
        "provider",
        "begin", "complete", "commit",
    ]
    assert events.index("provider") > events.index("claim")
    assert events.index("provider") < events.index("complete")


def test_generic_durable_job_remains_the_only_claim_lease_retry_mechanism():
    worker_source = Path("subsystems/jobs/durable_job_worker.py").read_text(encoding="utf-8")
    current_source = Path("subsystems/anomalies/current_issue_recheck.py").read_text(encoding="utf-8")

    assert "claim_next" in worker_source
    assert "claim_next" not in current_source
    assert "provider" not in current_source.lower()

from __future__ import annotations

from datetime import datetime, timezone

from domains.anomalies.current_issue import (
    CurrentIssueCandidate,
    CurrentIssueProjection,
    OwnerSnapshot,
    RecheckScope,
    build_issue_key,
)
from subsystems.anomalies.current_issue_recheck import CurrentIssueApplication


NOW = datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)
SUBJECT = {"case_no": "CASE-181", "notification_reason": "recipient_unavailable"}


def _scope() -> RecheckScope:
    return RecheckScope(
        "line",
        "notification_failure",
        "recipient_unavailable",
        ("CASE-181",),
        ("line:notification_failure:CASE-181",),
    )


def _candidate(lifecycle_token: str, owner_version: int) -> CurrentIssueCandidate:
    return CurrentIssueCandidate(
        build_issue_key("LINE-006", SUBJECT, lifecycle_token),
        "LINE-006",
        "line",
        "notification_failure",
        "recipient_unavailable",
        "CASE-181",
        owner_version,
        "warning",
        False,
        {"root_condition_active": True},
        SUBJECT,
    )


class _Uow:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self):
        pass


class _Repository:
    def __init__(self):
        self.snapshot = OwnerSnapshot(_scope(), "snapshot-1", 1, object())
        self.current = []

    def lock_scope(self, _scope):
        pass

    def release_scope(self, _scope):
        pass

    def read_owner_snapshot(self, _scope):
        return self.snapshot

    def assert_snapshot_current(self, _scope, snapshot_token):
        assert snapshot_token == self.snapshot.snapshot_token

    def list_current(self, _scope):
        return tuple(self.current)

    def upsert_current(self, candidate, verified_at):
        existing = next((row for row in self.current if row.issue_key == candidate.issue_key), None)
        started = existing.episode_started_at if existing else verified_at
        self.current = [row for row in self.current if row.issue_key != candidate.issue_key]
        self.current.append(CurrentIssueProjection(candidate, started, verified_at))

    def delete_current(self, issue_key):
        self.current = [row for row in self.current if row.issue_key != issue_key]


def test_same_active_lifecycle_keeps_identity_when_owner_snapshot_changes() -> None:
    repository = _Repository()
    application = CurrentIssueApplication(repository, _Uow, clock=lambda: NOW)

    first = application.reconcile(_scope(), lambda _snapshot: (_candidate("owner-state-1", 1),))
    repository.snapshot = OwnerSnapshot(_scope(), "snapshot-2", 2, object())
    second = application.reconcile(_scope(), lambda _snapshot: (_candidate("owner-state-2", 2),))

    assert first.present_issue_keys == second.present_issue_keys
    assert repository.current[0].candidate.owner_version == 2


def test_resolved_then_recurring_lifecycle_gets_a_new_identity() -> None:
    repository = _Repository()
    application = CurrentIssueApplication(repository, _Uow, clock=lambda: NOW)

    first = application.reconcile(_scope(), lambda _snapshot: (_candidate("owner-state-1", 1),))
    repository.snapshot = OwnerSnapshot(_scope(), "snapshot-resolved", 2, object())
    resolved = application.reconcile(_scope(), lambda _snapshot: ())
    repository.snapshot = OwnerSnapshot(_scope(), "snapshot-3", 3, object())
    recurring = application.reconcile(_scope(), lambda _snapshot: (_candidate("owner-state-3", 3),))

    assert resolved.present_issue_keys == ()
    assert first.present_issue_keys[0] != recurring.present_issue_keys[0]

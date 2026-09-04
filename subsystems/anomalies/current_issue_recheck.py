"""Application-owned reconciliation for current anomaly issues.

Repositories in this module are ports only: they never commit or roll back.
The application owns the transaction that reconciles present candidates,
deletes absent issues, and completes a previously committed recheck intent.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Protocol

from domains.anomalies.current_issue import (
    CurrentIssueCandidate,
    CurrentIssueProjection,
    OwnerSnapshot,
    RecheckIntent,
    RecheckScope,
    validate_candidate_set,
)
from shared_kernel.ports import UnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint


class CurrentIssueRecheckBlocked(RuntimeError):
    """The owner snapshot was not safe to use for a destructive reconciliation."""


class CurrentIssueRepository(Protocol):
    def lock_scope(self, scope: RecheckScope) -> None: ...

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot: ...

    def assert_snapshot_current(self, scope: RecheckScope, snapshot_token: str) -> None: ...

    def list_current(self, scope: RecheckScope) -> tuple[CurrentIssueProjection, ...]: ...

    def query_current(self, issue_key: str) -> CurrentIssueProjection | None: ...

    def upsert_current(self, candidate: CurrentIssueCandidate, verified_at: datetime) -> None: ...

    def delete_current(self, issue_key: str) -> None: ...

    def append_recheck_intent(self, intent: RecheckIntent) -> None: ...

    def complete_recheck_intent(self, intent: RecheckIntent) -> None: ...

    def release_scope(self, scope: RecheckScope) -> None: ...


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    present_issue_keys: tuple[str, ...]
    deleted_issue_keys: tuple[str, ...]
    owner_snapshot_token: str


def scope_from_payload(payload: dict[str, object]) -> RecheckScope:
    """Decode the closed generic durable-job payload at the worker boundary."""

    if not isinstance(payload, dict):
        raise ValueError("anomaly recheck payload must be an object")
    try:
        subject_ids = tuple(payload["subject_ids"])
        lock_keys = tuple(payload["owner_lock_keys"])
        return RecheckScope(
            payload["owner_domain"], payload["owner_root_type"],
            payload["subject_type"], subject_ids, lock_keys,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("anomaly recheck payload scope is invalid") from error


def recheck_intent_from_payload(payload: dict[str, object]) -> RecheckIntent:
    scope = scope_from_payload(payload)
    try:
        return RecheckIntent(
            payload["intent_identity"], scope, payload["owner_version"],
            PreviewFingerprint(payload["payload_fingerprint"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("anomaly recheck payload intent is invalid") from error


class CurrentIssueApplication:
    """Single commit owner for owner mutation intents and projection reconcile."""

    def __init__(
        self,
        repository: CurrentIssueRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def mutate_owner_with_recheck_intent(
        self,
        mutate_owner: Callable[[], object],
        intent: RecheckIntent,
    ) -> object:
        """Commit an owner mutation and its recheck intent atomically."""

        with self._unit_of_work_factory() as unit_of_work:
            result = mutate_owner()
            self._repository.append_recheck_intent(intent)
            unit_of_work.commit()
            return result

    def reconcile(
        self,
        scope: RecheckScope,
        detector: Callable[[OwnerSnapshot], tuple[CurrentIssueCandidate, ...]],
        *,
        completed_intent: RecheckIntent | None = None,
    ) -> ReconciliationResult:
        """Reconcile one complete owner snapshot in one application transaction."""

        try:
            with self._unit_of_work_factory() as unit_of_work:
                self._repository.lock_scope(scope)
                snapshot = self._repository.read_owner_snapshot(scope)
                if not isinstance(snapshot, OwnerSnapshot):
                    raise CurrentIssueRecheckBlocked("owner snapshot is invalid")
                if snapshot.scope != scope:
                    raise CurrentIssueRecheckBlocked("owner snapshot scope mismatch")
                if not snapshot.authoritative_complete:
                    raise CurrentIssueRecheckBlocked("owner snapshot is incomplete")
                self._repository.assert_snapshot_current(scope, snapshot.snapshot_token)
                if completed_intent is not None:
                    _validate_completed_intent(completed_intent, scope, snapshot)
                proposed = validate_candidate_set(scope, detector(snapshot))
                now = self._clock()
                current = self._repository.list_current(scope)
                candidates = _preserve_active_lifecycle_keys(scope, proposed, current)
                current_by_key = {item.issue_key: item for item in current}
                candidate_keys = {item.issue_key for item in candidates}
                deleted = tuple(sorted(set(current_by_key) - candidate_keys))
                for candidate in candidates:
                    self._repository.upsert_current(candidate, now)
                for issue_key in deleted:
                    # Predicate absence is represented by deletion, never a terminal
                    # issue row or a second anomaly-owned state machine.
                    self._repository.delete_current(issue_key)
                if completed_intent is not None:
                    self._repository.complete_recheck_intent(completed_intent)
                unit_of_work.commit()
        finally:
            release_scope = getattr(self._repository, "release_scope", None)
            if release_scope is not None:
                release_scope(scope)
        return ReconciliationResult(
            tuple(candidate.issue_key for candidate in candidates),
            deleted,
            snapshot.snapshot_token,
        )


def _preserve_active_lifecycle_keys(
    scope: RecheckScope,
    candidates: tuple[CurrentIssueCandidate, ...],
    current: tuple[CurrentIssueProjection, ...],
) -> tuple[CurrentIssueCandidate, ...]:
    """Reuse the persisted key while the same canonical subject remains active."""

    current_by_subject = {
        (item.candidate.definition_code, item.candidate.canonical_subject_identity): item.issue_key
        for item in current
    }
    stable = tuple(
        replace(
            candidate,
            issue_key=current_by_subject.get(
                (candidate.definition_code, candidate.canonical_subject_identity),
                candidate.issue_key,
            ),
        )
        for candidate in candidates
    )
    return validate_candidate_set(scope, stable)


def _validate_completed_intent(
    intent: RecheckIntent,
    scope: RecheckScope,
    snapshot: OwnerSnapshot,
) -> None:
    """Prevent a recheck from completing an intent for another owner scope.

    An intent is created in the owner mutation transaction and may be replayed
    against a newer owner snapshot.  It must never be marked complete by a
    different scope or by a snapshot older than the owner version recorded by
    the intent.
    """

    if not isinstance(intent, RecheckIntent):
        raise CurrentIssueRecheckBlocked("recheck intent is invalid")
    if intent.scope != scope:
        raise CurrentIssueRecheckBlocked("recheck intent scope mismatch")
    if intent.owner_version > snapshot.owner_version:
        raise CurrentIssueRecheckBlocked("recheck intent owner version is newer than snapshot")


__all__ = [
    "CurrentIssueApplication",
    "CurrentIssueRecheckBlocked",
    "CurrentIssueRepository",
    "ReconciliationResult",
    "recheck_intent_from_payload",
    "scope_from_payload",
]

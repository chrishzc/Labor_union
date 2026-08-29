"""Application-owned reconciliation for current anomaly issues.

Repositories in this module are ports only: they never commit or roll back.
The application owns the transaction that reconciles present candidates,
deletes absent issues, and completes a previously committed recheck intent.
"""

from __future__ import annotations

from dataclasses import dataclass
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


class CurrentIssueRecheckBlocked(RuntimeError):
    """The owner snapshot was not safe to use for a destructive reconciliation."""


class CurrentIssueRepository(Protocol):
    def lock_scope(self, scope: RecheckScope) -> None: ...

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot: ...

    def assert_snapshot_current(self, scope: RecheckScope, snapshot_token: str) -> None: ...

    def list_current(self, scope: RecheckScope) -> tuple[CurrentIssueProjection, ...]: ...

    def upsert_current(self, candidate: CurrentIssueCandidate, verified_at: datetime) -> None: ...

    def delete_current(self, issue_key: str) -> None: ...

    def append_recheck_intent(self, intent: RecheckIntent) -> None: ...

    def complete_recheck_intent(self, intent: RecheckIntent) -> None: ...


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    present_issue_keys: tuple[str, ...]
    deleted_issue_keys: tuple[str, ...]
    owner_snapshot_token: str


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

        with self._unit_of_work_factory() as unit_of_work:
            self._repository.lock_scope(scope)
            snapshot = self._repository.read_owner_snapshot(scope)
            if snapshot.scope != scope:
                raise CurrentIssueRecheckBlocked("owner snapshot scope mismatch")
            if not snapshot.authoritative_complete:
                raise CurrentIssueRecheckBlocked("owner snapshot is incomplete")
            self._repository.assert_snapshot_current(scope, snapshot.snapshot_token)
            candidates = validate_candidate_set(scope, detector(snapshot))
            now = self._clock()
            current = self._repository.list_current(scope)
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
        return ReconciliationResult(
            tuple(candidate.issue_key for candidate in candidates),
            deleted,
            snapshot.snapshot_token,
        )


__all__ = [
    "CurrentIssueApplication",
    "CurrentIssueRecheckBlocked",
    "CurrentIssueRepository",
    "ReconciliationResult",
]

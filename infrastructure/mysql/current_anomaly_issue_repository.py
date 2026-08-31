"""MySQL adapter for the additive, current-only anomaly projection.

The adapter owns SQL only.  It never commits or rolls back; the anomaly
application owns the transaction which locks, reconciles, and completes an
intent.  Owner facts are supplied by an explicit composition callback because
this adapter must not invent a cross-domain owner query.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
from typing import Any

from domains.anomalies.current_issue import (
    CurrentIssueCandidate,
    CurrentIssueProjection,
    OwnerSnapshot,
    RecheckIntent,
    RecheckScope,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.durable_job_queue import DurableJobCommand
from infrastructure.mysql.background_job_repository import BackgroundJobRepository


class CurrentIssueOwnerSnapshotUnavailable(RuntimeError):
    """No authoritative owner readback was composed for this scope."""


class CurrentIssueMySqlUnitOfWork(MySqlUnitOfWork):
    """Named composition type for current-issue application transactions."""


class MySqlCurrentIssueRepository:
    """Persistence port implementation for ``current_anomaly_issues``."""

    def __init__(
        self,
        connection,
        *,
        owner_snapshot_reader: Callable[[RecheckScope], OwnerSnapshot] | None = None,
    ) -> None:
        self._connection = connection
        self._owner_snapshot_reader = owner_snapshot_reader
        self._snapshot: OwnerSnapshot | None = None
        self._held_locks: tuple[str, ...] = ()

    def lock_scope(self, scope: RecheckScope) -> None:
        """Acquire all owner-root locks in canonical byte order.

        MySQL named locks are used because the approved successor deliberately
        adds no owner-lock or anomaly-history table.  They are released by the
        application after its transaction exits.
        """

        lock_keys = tuple(sorted(scope.owner_lock_keys, key=lambda item: item.encode("utf-8")))
        acquired: list[str] = []
        try:
            with _cursor(self._connection) as cursor:
                for key in lock_keys:
                    cursor.execute("SELECT GET_LOCK(%s, 0)", ("anomaly-owner:" + key,))
                    row = cursor.fetchone()
                    result = row[0] if not isinstance(row, dict) else next(iter(row.values()))
                    if result != 1:
                        raise CurrentIssueOwnerSnapshotUnavailable("anomaly owner scope lock unavailable")
                    acquired.append(key)
        except Exception:
            self._release_locks(acquired)
            raise
        self._held_locks = tuple(acquired)

    def release_scope(self, scope: RecheckScope) -> None:
        del scope
        self._release_locks(self._held_locks)
        self._held_locks = ()

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot:
        if self._owner_snapshot_reader is None:
            raise CurrentIssueOwnerSnapshotUnavailable("anomaly owner snapshot reader not composed")
        snapshot = self._owner_snapshot_reader(scope)
        if not isinstance(snapshot, OwnerSnapshot):
            raise CurrentIssueOwnerSnapshotUnavailable("anomaly owner snapshot is invalid")
        self._snapshot = snapshot
        return snapshot

    def assert_snapshot_current(self, scope: RecheckScope, snapshot_token: str) -> None:
        if self._owner_snapshot_reader is None:
            raise CurrentIssueOwnerSnapshotUnavailable("anomaly owner snapshot reader not composed")
        current = self._owner_snapshot_reader(scope)
        if not isinstance(current, OwnerSnapshot) or current.snapshot_token != snapshot_token:
            raise CurrentIssueOwnerSnapshotUnavailable("anomaly owner snapshot is stale")
        self._snapshot = current

    def list_current(self, scope: RecheckScope) -> tuple[CurrentIssueProjection, ...]:
        placeholders = ",".join("%s" for _ in scope.subject_ids)
        sql = (
            "SELECT issue_key, definition_code, owner_domain, owner_root_type, "
            "subject_type, subject_id, subject_identity, owner_snapshot_token, "
            "owner_version, severity, blocking, details_version, details, "
            "episode_started_at, last_verified_at "
            "FROM current_anomaly_issues WHERE owner_domain=%s AND owner_root_type=%s "
            "AND subject_type=%s AND subject_id IN (" + placeholders + ") "
            "AND definition_code='LINE-006' ORDER BY issue_key"
        )
        with _cursor(self._connection) as cursor:
            cursor.execute(sql, (scope.owner_domain, scope.owner_root_type, scope.subject_type, *scope.subject_ids))
            rows = tuple(cursor.fetchall())
        return tuple(_projection(row) for row in rows)

    def query_current(self, issue_key: str) -> CurrentIssueProjection | None:
        """Read one current issue by its opaque public key.

        This is intentionally a primary-key lookup against the current-only
        projection.  It does not consult legacy fingerprints, snapshots, or
        any occurrence/workflow table.
        """

        if not isinstance(issue_key, str) or not issue_key.startswith("ci_"):
            raise ValueError("current issue key is invalid")
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT issue_key, definition_code, owner_domain, owner_root_type, "
                "subject_type, subject_id, subject_identity, owner_snapshot_token, "
                "owner_version, severity, blocking, details_version, details, "
                "episode_started_at, last_verified_at "
                "FROM current_anomaly_issues WHERE issue_key=%s AND definition_code='LINE-006'",
                (issue_key,),
            )
            row = cursor.fetchone()
        return None if row is None else _projection(row)

    def query_current_page(self, request, after, fetch_limit: int):
        """Read one bounded keyset page from the current-only projection."""
        conditions: list[str] = []
        parameters: list[object] = []
        # Current public projection is closed to LINE-006. Older rows remain
        # migration evidence, but never become visible through this query.
        conditions.append("definition_code='LINE-006'")
        if request.definition_code is not None:
            conditions.append("definition_code=%s")
            parameters.append(request.definition_code)
        if request.owner_domain is not None:
            conditions.append("owner_domain=%s")
            parameters.append(request.owner_domain)
        if request.blocking is not None:
            conditions.append("blocking=%s")
            parameters.append(int(request.blocking))
        severity_rank = "CASE severity WHEN 'blocking' THEN 2 WHEN 'warning' THEN 1 ELSE 0 END"
        if after is not None:
            last_blocking, last_severity, last_started, last_key = after
            conditions.append(
                "(blocking<%s OR (blocking=%s AND " + severity_rank + "<%s) OR "
                "(blocking=%s AND " + severity_rank + "=%s AND episode_started_at>%s) OR "
                "(blocking=%s AND " + severity_rank + "=%s AND episode_started_at=%s AND issue_key>%s))"
            )
            parameters.extend(
                (
                    last_blocking,
                    last_blocking,
                    last_severity,
                    last_blocking,
                    last_severity,
                    _naive_utc(last_started),
                    last_blocking,
                    last_severity,
                    _naive_utc(last_started),
                    last_key,
                )
            )
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sql = (
            "SELECT issue_key, definition_code, owner_domain, owner_root_type, "
            "subject_type, subject_id, subject_identity, owner_snapshot_token, "
            "owner_version, severity, blocking, details_version, details, "
            "episode_started_at, last_verified_at FROM current_anomaly_issues"
            + where
            + " ORDER BY blocking DESC, "
            + severity_rank
            + " DESC, episode_started_at ASC, issue_key ASC LIMIT %s"
        )
        parameters.append(fetch_limit)
        with _cursor(self._connection) as cursor:
            cursor.execute(sql, tuple(parameters))
            return tuple(_projection(row) for row in cursor.fetchall())

    def upsert_current(self, candidate: CurrentIssueCandidate, verified_at: datetime) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            raise CurrentIssueOwnerSnapshotUnavailable("current issue upsert lacks owner snapshot")
        if candidate.subject_identity is None:
            raise CurrentIssueOwnerSnapshotUnavailable(
                "current issue upsert lacks canonical subject identity"
            )
        subject_json = candidate.canonical_subject_identity
        details_json = _json_dump(candidate.details)
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO current_anomaly_issues "
                "(issue_key,definition_code,owner_domain,owner_root_type,subject_type,subject_id,"
                "subject_identity,owner_snapshot_token,owner_version,severity,blocking,details_version,"
                "details,episode_started_at,last_verified_at) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE definition_code=VALUES(definition_code), "
                "owner_domain=VALUES(owner_domain), owner_root_type=VALUES(owner_root_type), "
                "subject_type=VALUES(subject_type), subject_id=VALUES(subject_id), "
                "subject_identity=VALUES(subject_identity), owner_snapshot_token=VALUES(owner_snapshot_token), "
                "owner_version=VALUES(owner_version), severity=VALUES(severity), blocking=VALUES(blocking), "
                "details_version=VALUES(details_version), details=VALUES(details), "
                "last_verified_at=VALUES(last_verified_at)",
                (
                    candidate.issue_key, candidate.definition_code, candidate.owner_domain,
                    candidate.owner_root_type, candidate.subject_type, candidate.subject_id,
                    subject_json, snapshot.snapshot_token, candidate.owner_version,
                    candidate.severity, int(candidate.blocking), details_json,
                    _naive_utc(verified_at), _naive_utc(verified_at),
                ),
            )

    def delete_current(self, issue_key: str) -> None:
        with _cursor(self._connection) as cursor:
            cursor.execute("DELETE FROM current_anomaly_issues WHERE issue_key=%s", (issue_key,))

    def append_recheck_intent(self, intent: RecheckIntent) -> None:
        payload = {
            "intent_identity": intent.intent_identity,
            "owner_domain": intent.scope.owner_domain,
            "owner_root_type": intent.scope.owner_root_type,
            "subject_type": intent.scope.subject_type,
            "subject_ids": list(intent.scope.subject_ids),
            "owner_lock_keys": list(intent.scope.owner_lock_keys),
            "owner_version": intent.owner_version,
            "payload_fingerprint": intent.payload_fingerprint.value,
        }
        BackgroundJobRepository(self._connection).enqueue_canonical_command(
            DurableJobCommand(
                _job_id(intent.intent_identity),
                intent.intent_identity,
                "anomaly.recheck",
                1,
                payload,
                "system:anomaly-recheck",
                intent.intent_identity,
            )
        )

    def complete_recheck_intent(self, intent: RecheckIntent) -> None:
        """Record application completion while generic worker owns terminal state.

        The worker still performs the lease-guarded terminal transition after
        the handler returns.  This marker is intentionally kept in the generic
        queue row and is therefore not an anomaly history table.
        """

        with _cursor(self._connection) as cursor:
            cursor.execute(
                "UPDATE background_jobs SET result_reference=%s "
                "WHERE command_identity=%s AND status IN ('queued','running')",
                ("anomaly-recheck:" + intent.intent_identity, intent.intent_identity),
            )

    def _release_locks(self, lock_keys: list[str] | tuple[str, ...]) -> None:
        if not lock_keys:
            return
        with _cursor(self._connection) as cursor:
            for key in reversed(lock_keys):
                cursor.execute("SELECT RELEASE_LOCK(%s)", ("anomaly-owner:" + key,))


# The longer alias mirrors the persisted table name and keeps the adapter
# discoverable without introducing a second implementation.
MySqlCurrentAnomalyIssueRepository = MySqlCurrentIssueRepository
CurrentAnomalyIssueMySqlUnitOfWork = CurrentIssueMySqlUnitOfWork


def _projection(row: Any) -> CurrentIssueProjection:
    details = _json_object(_value(row, "details", 12))
    identity = _json_object(_value(row, "subject_identity", 6))
    candidate = CurrentIssueCandidate(
        str(_value(row, "issue_key", 0)),
        str(_value(row, "definition_code", 1)),
        str(_value(row, "owner_domain", 2)),
        str(_value(row, "owner_root_type", 3)),
        str(_value(row, "subject_type", 4)),
        str(_value(row, "subject_id", 5)),
        int(_value(row, "owner_version", 8)),
        str(_value(row, "severity", 9)),
        bool(_value(row, "blocking", 10)),
        details,
        identity,
    )
    return CurrentIssueProjection(
        candidate,
        _aware_utc(_value(row, "episode_started_at", 13)),
        _aware_utc(_value(row, "last_verified_at", 14)),
        str(_value(row, "owner_snapshot_token", 7)),
        int(_value(row, "details_version", 11)),
    )


def _job_id(identity: str) -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return "anomaly-recheck:" + digest


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("current anomaly JSON value must be an object")
    return parsed


def _value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, dict) else row[index]


def _aware_utc(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("current anomaly timestamp is invalid")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("current anomaly timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@contextmanager
def _cursor(connection) -> Iterator[Any]:
    with connection.cursor() as cursor:
        yield cursor


__all__ = [
    "CurrentIssueMySqlUnitOfWork",
    "CurrentAnomalyIssueMySqlUnitOfWork",
    "CurrentIssueOwnerSnapshotUnavailable",
    "MySqlCurrentAnomalyIssueRepository",
    "MySqlCurrentIssueRepository",
]

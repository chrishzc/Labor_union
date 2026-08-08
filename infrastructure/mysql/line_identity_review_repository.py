"""MySQL adapters for canonical LINE identity bindings and human reviews."""

from __future__ import annotations

from typing import Any

from domains.line.identities import LineReviewRequestId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
    LineIdentityClaim,
    transition_binding_status,
)
from domains.line.review import (
    LineReviewDecisionCandidate,
    LineReviewSnapshot,
    LineReviewStatus,
    LineReviewType,
)
from infrastructure.mysql.line_repository_support import optional_row
from shared_kernel.identities import ExpectedVersion
from subsystems.line.review_contracts import (
    DecideLineReviewCommand,
    DecideLineReviewResult,
    LineReviewCommandOutcome,
    LineReviewListQuery,
    LineReviewPage,
)


class MySqlLineIdentityRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, line_user_id: LineUserId) -> LineIdentityBindingSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_IDENTITY_SELECT_SQL, (line_user_id.value,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _identity_snapshot(row)

    def save_claim(
        self,
        claim: LineIdentityClaim,
        expected_version: ExpectedVersion,
    ) -> LineIdentityBindingSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_IDENTITY_SELECT_SQL + " FOR UPDATE", (claim.line_user_id.value,))
            row = optional_row(cursor.fetchone())
            snapshot = _initial_identity(claim.line_user_id) if row is None else _identity_snapshot(row)
            if _claim_already_saved(snapshot, claim):
                return snapshot
            if snapshot.version != expected_version:
                raise RuntimeError("line_identity_binding_conflict")
            target = transition_binding_status(
                snapshot.status,
                LineIdentityBindingStatus.PENDING_REVIEW,
            )
            self._persist_claim(cursor, snapshot, claim, target, is_new=row is None)
        return LineIdentityBindingSnapshot(
            claim.line_user_id,
            target,
            ExpectedVersion(expected_version.value + 1),
            claim.subject_type,
            claim.subject_reference,
        )

    def _persist_claim(self, cursor, snapshot, claim, target, *, is_new):
        resulting_version = snapshot.version.value + 1
        if is_new:
            cursor.execute(
                _IDENTITY_INSERT_SQL,
                (
                    claim.line_user_id.value,
                    target.value,
                    claim.subject_type.value,
                    claim.subject_reference,
                    resulting_version,
                ),
            )
        else:
            cursor.execute(
                _IDENTITY_UPDATE_SQL,
                (
                    target.value,
                    claim.subject_type.value,
                    claim.subject_reference,
                    resulting_version,
                    claim.line_user_id.value,
                    snapshot.version.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_identity_binding_conflict")
        cursor.execute(
            _IDENTITY_EVENT_INSERT_SQL,
            (
                claim.line_user_id.value,
                claim.subject_type.value,
                claim.subject_reference,
                snapshot.version.value,
                resulting_version,
                claim.fingerprint.value,
                f"line-identity-claim:{claim.fingerprint.value}:{resulting_version}",
                f"line-identity-claim:{claim.fingerprint.value}",
            ),
        )


class MySqlLineIdentityReviewRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, request_id: LineReviewRequestId) -> LineReviewSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_REVIEW_SELECT_SQL, (request_id.value,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _review_snapshot(row)

    def list(self, query: LineReviewListQuery) -> LineReviewPage:
        sql, parameters = _review_list_statement(query)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            rows = tuple(cursor.fetchall() or ())
        has_more = len(rows) > query.page_size
        visible_rows = rows[: query.page_size]
        items = tuple(_review_snapshot(row) for row in visible_rows)
        next_cursor = str(visible_rows[-1]["id"]) if has_more else None
        return LineReviewPage(items, next_cursor)

    def decide(
        self,
        command: DecideLineReviewCommand,
        candidate: LineReviewDecisionCandidate,
    ) -> DecideLineReviewResult:
        with self._connection.cursor() as cursor:
            existing = self._existing_decision(cursor, command)
            if existing is not None:
                if str(existing["decision_fingerprint"]) != candidate.fingerprint.value:
                    raise RuntimeError("line_review_idempotency_conflict")
                return DecideLineReviewResult(LineReviewCommandOutcome.EXISTING, candidate)
            cursor.execute(
                _REVIEW_UPDATE_SQL,
                (
                    candidate.after_status.value,
                    candidate.resulting_version.value,
                    command.actor.actor_id,
                    command.reason,
                    command.request_id.value,
                    candidate.expected_version.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_review_candidate_stale")
            self._append_decision(cursor, command, candidate)
        return DecideLineReviewResult(LineReviewCommandOutcome.CREATED, candidate)

    def _existing_decision(self, cursor, command):
        cursor.execute(_REVIEW_DECISION_SELECT_SQL, (command.idempotency_key.value,))
        return optional_row(cursor.fetchone())

    def _append_decision(self, cursor, command, candidate):
        cursor.execute(
            _REVIEW_DECISION_INSERT_SQL,
            (
                command.request_id.value,
                candidate.before_status.value,
                candidate.after_status.value,
                candidate.expected_version.value,
                candidate.resulting_version.value,
                command.actor.actor_id,
                command.reason,
                candidate.fingerprint.value,
                command.idempotency_key.value,
                command.correlation_id.value,
            ),
        )


def _initial_identity(line_user_id):
    return LineIdentityBindingSnapshot(
        line_user_id,
        LineIdentityBindingStatus.UNBOUND,
        ExpectedVersion(0),
    )


def _claim_already_saved(snapshot, claim):
    return (
        snapshot.status in {
            LineIdentityBindingStatus.PENDING_REVIEW,
            LineIdentityBindingStatus.BOUND,
        }
        and snapshot.subject_type is claim.subject_type
        and snapshot.subject_reference == claim.subject_reference
    )


def _identity_snapshot(row):
    subject_type = row.get("subject_type")
    return LineIdentityBindingSnapshot(
        LineUserId(str(row["line_user_id"])),
        LineIdentityBindingStatus(str(row["binding_status"])),
        ExpectedVersion(int(row["aggregate_version"])),
        LineBindingSubjectType(str(subject_type)) if subject_type is not None else None,
        _optional_text(row.get("subject_reference")),
    )


def _review_snapshot(row):
    return LineReviewSnapshot(
        LineReviewRequestId(int(row["id"])),
        LineReviewType(str(row["review_type"])),
        LineReviewStatus(str(row["review_status"])),
        ExpectedVersion(int(row["aggregate_version"])),
    )


def _review_list_statement(query):
    clauses = []
    parameters: list[object] = []
    if query.statuses:
        clauses.append("review_status IN (" + ",".join(["%s"] * len(query.statuses)) + ")")
        parameters.extend(item.value for item in query.statuses)
    if query.review_types:
        clauses.append("review_type IN (" + ",".join(["%s"] * len(query.review_types)) + ")")
        parameters.extend(item.value for item in query.review_types)
    if query.cursor is not None:
        clauses.append("id < %s")
        parameters.append(int(query.cursor))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    parameters.append(query.page_size + 1)
    return _REVIEW_LIST_SQL + where + " ORDER BY id DESC LIMIT %s", tuple(parameters)


def _optional_text(value):
    return None if value is None else str(value)


_IDENTITY_SELECT_SQL = (
    "SELECT line_user_id,binding_status,subject_type,subject_reference,"
    "aggregate_version FROM line_identity_bindings WHERE line_user_id=%s"
)
_IDENTITY_INSERT_SQL = (
    "INSERT INTO line_identity_bindings (line_user_id,binding_status,subject_type,"
    "subject_reference,aggregate_version) VALUES (%s,%s,%s,%s,%s)"
)
_IDENTITY_UPDATE_SQL = (
    "UPDATE line_identity_bindings SET binding_status=%s,subject_type=%s,"
    "subject_reference=%s,aggregate_version=%s WHERE line_user_id=%s "
    "AND aggregate_version=%s"
)
_IDENTITY_EVENT_INSERT_SQL = (
    "INSERT INTO line_identity_binding_events (line_user_id,action,subject_type,"
    "subject_reference,expected_version,resulting_version,actor_id,"
    "payload_fingerprint,idempotency_key,correlation_id) "
    "VALUES (%s,'claim_submitted',%s,%s,%s,%s,'line-platform',%s,%s,%s)"
)
_REVIEW_SELECT_SQL = (
    "SELECT id,review_type,review_status,aggregate_version "
    "FROM line_review_requests WHERE id=%s"
)
_REVIEW_LIST_SQL = (
    "SELECT id,review_type,review_status,aggregate_version FROM line_review_requests"
)
_REVIEW_UPDATE_SQL = (
    "UPDATE line_review_requests SET review_status=%s,aggregate_version=%s,"
    "reviewed_by_actor_id=%s,decision_reason=%s,reviewed_at_utc=CURRENT_TIMESTAMP(6) "
    "WHERE id=%s AND aggregate_version=%s AND review_status='pending'"
)
_REVIEW_DECISION_SELECT_SQL = (
    "SELECT decision_fingerprint FROM line_review_decision_events "
    "WHERE idempotency_key=%s"
)
_REVIEW_DECISION_INSERT_SQL = (
    "INSERT INTO line_review_decision_events (review_request_id,before_status,"
    "after_status,expected_version,resulting_version,actor_id,reason,"
    "decision_fingerprint,idempotency_key,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)


__all__ = [
    "MySqlLineIdentityRepository",
    "MySqlLineIdentityReviewRepository",
]

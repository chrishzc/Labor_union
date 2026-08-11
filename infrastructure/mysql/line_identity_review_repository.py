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
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from infrastructure.mysql.line_repository_support import optional_row
from shared_kernel.identities import ExpectedVersion
from subsystems.line.review_contracts import (
    CreateLineReviewCommand,
    CreateLineReviewResult,
    DecideLineReviewCommand,
    DecideLineReviewResult,
    LineReviewCommandOutcome,
    LineReviewListQuery,
    LineReviewPage,
    LineReviewQueueSummary,
)


class MySqlLineIdentityRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, line_user_id: LineUserId) -> LineIdentityBindingSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_IDENTITY_SELECT_SQL, (line_user_id.value,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _identity_snapshot(row)

    def get_by_subject(self, subject_type, subject_reference):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _IDENTITY_SELECT_BY_SUBJECT_SQL,
                (subject_type.value, subject_reference),
            )
            row = optional_row(cursor.fetchone())
        return None if row is None else _identity_snapshot(row)

    def list_bound_by_subject_type(self, subject_type):
        with self._connection.cursor() as cursor:
            cursor.execute(_IDENTITY_LIST_BOUND_SQL, (subject_type.value,))
            rows = tuple(cursor.fetchall() or ())
        return tuple(_identity_snapshot(row) for row in rows)

    # Kept cohesive because the row lock, transition, and event form one repository write.
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

    def bind(
        self,
        claim,
        expected_version,
        actor_id,
        idempotency_key,
        correlation_id,
    ):
        return self._transition_binding(
            claim,
            expected_version,
            LineIdentityBindingStatus.BOUND,
            "bound",
            actor_id,
            idempotency_key,
            correlation_id,
        )

    # Kept cohesive because replay validation and optimistic revoke share the same lock.
    def revoke(
        self,
        line_user_id,
        expected_version,
        actor_id,
        idempotency_key,
        correlation_id,
    ):
        with self._connection.cursor() as cursor:
            existing = self._existing_event(cursor, idempotency_key.value)
            if existing is not None:
                snapshot = self.get(line_user_id)
                if snapshot is None:
                    raise RuntimeError("line_identity_binding_missing")
                _require_same_transition_event(
                    existing,
                    snapshot,
                    LineIdentityBindingStatus.REVOKED,
                    "revoked",
                    actor_id,
                )
                return snapshot
            cursor.execute(_IDENTITY_SELECT_SQL + " FOR UPDATE", (line_user_id.value,))
            row = optional_row(cursor.fetchone())
            if row is None:
                raise LookupError("line_identity_binding_not_found")
            snapshot = _identity_snapshot(row)
            if snapshot.status is LineIdentityBindingStatus.REVOKED:
                return snapshot
            if snapshot.version != expected_version:
                raise RuntimeError("line_identity_binding_conflict")
            target = transition_binding_status(snapshot.status, LineIdentityBindingStatus.REVOKED)
            resulting_version = expected_version.value + 1
            cursor.execute(
                _IDENTITY_STATUS_UPDATE_SQL,
                (target.value, resulting_version, line_user_id.value, expected_version.value),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_identity_binding_conflict")
            self._append_transition_event(
                cursor,
                snapshot,
                target,
                "revoked",
                actor_id,
                idempotency_key.value,
                correlation_id,
            )
        return LineIdentityBindingSnapshot(
            line_user_id,
            target,
            ExpectedVersion(resulting_version),
            snapshot.subject_type,
            snapshot.subject_reference,
        )

    # Kept cohesive because splitting would hide the lock-to-event atomicity invariant.
    def _transition_binding(
        self,
        claim,
        expected_version,
        target,
        action,
        actor_id,
        idempotency_key,
        correlation_id,
    ):
        with self._connection.cursor() as cursor:
            existing = self._existing_event(cursor, idempotency_key.value)
            if existing is not None:
                snapshot = self.get(claim.line_user_id)
                if snapshot is None:
                    raise RuntimeError("line_identity_binding_missing")
                replay_snapshot = LineIdentityBindingSnapshot(
                    claim.line_user_id,
                    snapshot.status,
                    snapshot.version,
                    claim.subject_type,
                    claim.subject_reference,
                )
                _require_same_transition_event(
                    existing,
                    replay_snapshot,
                    target,
                    action,
                    actor_id,
                )
                return snapshot
            cursor.execute(_IDENTITY_SELECT_SQL + " FOR UPDATE", (claim.line_user_id.value,))
            row = optional_row(cursor.fetchone())
            snapshot = _initial_identity(claim.line_user_id) if row is None else _identity_snapshot(row)
            if snapshot.status is target and _claim_already_saved(snapshot, claim):
                return snapshot
            if snapshot.version != expected_version:
                raise RuntimeError("line_identity_binding_conflict")
            _require_claim_matches_snapshot(snapshot, claim)
            transition_binding_status(snapshot.status, target)
            resulting_version = expected_version.value + 1
            self._persist_binding_transition(cursor, snapshot, claim, target, resulting_version, row is None)
            self._append_transition_event(
                cursor,
                LineIdentityBindingSnapshot(
                    snapshot.line_user_id,
                    snapshot.status,
                    snapshot.version,
                    claim.subject_type,
                    claim.subject_reference,
                ),
                target,
                action,
                actor_id,
                idempotency_key.value,
                correlation_id,
            )
        return LineIdentityBindingSnapshot(
            claim.line_user_id,
            target,
            ExpectedVersion(resulting_version),
            claim.subject_type,
            claim.subject_reference,
        )

    def _persist_binding_transition(self, cursor, snapshot, claim, target, version, is_new):
        if is_new:
            cursor.execute(
                _IDENTITY_INSERT_SQL,
                (claim.line_user_id.value, target.value, claim.subject_type.value, claim.subject_reference, version),
            )
            return
        cursor.execute(
            _IDENTITY_UPDATE_SQL,
            (target.value, claim.subject_type.value, claim.subject_reference, version,
             claim.line_user_id.value, snapshot.version.value),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("line_identity_binding_conflict")

    def _existing_event(self, cursor, idempotency_key):
        cursor.execute(_IDENTITY_EVENT_SELECT_SQL, (idempotency_key,))
        return optional_row(cursor.fetchone())

    def _append_transition_event(
        self, cursor, snapshot, target, action, actor_id, idempotency_key, correlation_id
    ):
        resulting_version = snapshot.version.value + 1
        fingerprint = _transition_fingerprint(snapshot, target, action, actor_id)
        cursor.execute(
            _IDENTITY_TRANSITION_EVENT_INSERT_SQL,
            (
                snapshot.line_user_id.value,
                action,
                snapshot.subject_type.value if snapshot.subject_type else None,
                snapshot.subject_reference,
                snapshot.version.value,
                resulting_version,
                actor_id,
                fingerprint.value,
                idempotency_key,
                correlation_id,
            ),
        )

    # Kept cohesive so aggregate and immutable claim event always advance one version.
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

    # Kept cohesive because replay validation and insert-readback are one idempotent write.
    def create(self, command: CreateLineReviewCommand) -> CreateLineReviewResult:
        with self._connection.cursor() as cursor:
            cursor.execute(_REVIEW_SELECT_BY_FLOW_SQL, (command.flow_id.value,))
            existing = optional_row(cursor.fetchone())
            if existing is not None:
                _require_same_review_request(existing, command)
                return CreateLineReviewResult(
                    LineReviewCommandOutcome.EXISTING,
                    _review_snapshot(existing),
                )
            cursor.execute(
                _REVIEW_INSERT_SQL,
                (
                    command.review_type.value,
                    command.line_user_id.value,
                    command.subject_type.value,
                    command.subject_reference,
                    command.request_fingerprint.value,
                    command.evidence_json,
                    command.flow_id.value,
                    command.idempotency_key.value,
                    command.correlation_id.value,
                ),
            )
            request_id = int(cursor.lastrowid)
            cursor.execute(_REVIEW_SELECT_SQL, (request_id,))
            row = optional_row(cursor.fetchone())
        if row is None:
            raise RuntimeError("line_review_request_missing_after_insert")
        return CreateLineReviewResult(LineReviewCommandOutcome.CREATED, _review_snapshot(row))

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

    def summary(self, stale_hours: int) -> LineReviewQueueSummary:
        with self._connection.cursor() as cursor:
            cursor.execute(_REVIEW_SUMMARY_SQL, (stale_hours,))
            row = optional_row(cursor.fetchone()) or {}
        return LineReviewQueueSummary(
            int(row.get("pending_total") or 0),
            int(row.get("staff_pending") or 0),
            int(row.get("rebind_pending") or 0),
            int(row.get("processed_today") or 0),
            int(row.get("stale_pending") or 0),
            stale_hours,
        )

    # Kept cohesive because review update and immutable decision event must be atomic.
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


def _require_claim_matches_snapshot(snapshot, claim):
    if snapshot.subject_type is None:
        return
    if snapshot.subject_type is not claim.subject_type:
        raise RuntimeError("line_identity_subject_conflict")
    if snapshot.subject_reference != claim.subject_reference:
        raise RuntimeError("line_identity_subject_conflict")


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
        LineUserId(str(row["line_user_id"])),
        LineBindingSubjectType(str(row["subject_type"])),
        str(row["subject_reference"]),
        PreviewFingerprint(str(row["request_fingerprint"])),
        str(row.get("evidence_snapshot") or "{}"),
        int(row["assigned_admin_id"]) if row.get("assigned_admin_id") is not None else None,
        row.get("assigned_at_utc"),
        row.get("due_at_utc"),
        int(row.get("reassignment_count") or 0),
        _optional_text(row.get("reviewed_by_actor_id")),
        _optional_text(row.get("decision_reason")),
        row.get("reviewed_at_utc"),
        row.get("created_at_utc"),
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


def _transition_fingerprint(snapshot, target, action, actor_id):
    return fingerprint_payload(
        {
            "action": action,
            "actor_id": actor_id,
            "line_user_id": snapshot.line_user_id.value,
            "subject_type": snapshot.subject_type.value if snapshot.subject_type else None,
            "subject_reference": snapshot.subject_reference,
            "target_status": target.value,
        }
    )


def _require_same_transition_event(existing, snapshot, target, action, actor_id):
    expected = _transition_fingerprint(snapshot, target, action, actor_id)
    if str(existing["line_user_id"]) != snapshot.line_user_id.value:
        raise RuntimeError("line_identity_event_idempotency_conflict")
    if str(existing["payload_fingerprint"]) != expected.value:
        raise RuntimeError("line_identity_event_idempotency_conflict")


def _require_same_review_request(existing, command):
    if str(existing["request_fingerprint"]) != command.request_fingerprint.value:
        raise RuntimeError("line_review_request_idempotency_conflict")


_IDENTITY_SELECT_SQL = (
    "SELECT line_user_id,binding_status,subject_type,subject_reference,"
    "aggregate_version FROM line_identity_bindings WHERE line_user_id=%s"
)
_IDENTITY_SELECT_BY_SUBJECT_SQL = (
    _IDENTITY_SELECT_SQL.replace("WHERE line_user_id=%s", "WHERE subject_type=%s AND subject_reference=%s ")
    + "AND binding_status IN ('pending_review','bound') LIMIT 1"
)
_IDENTITY_LIST_BOUND_SQL = (
    "SELECT line_user_id,binding_status,subject_type,subject_reference,"
    "aggregate_version FROM line_identity_bindings "
    "WHERE subject_type=%s AND binding_status='bound' ORDER BY line_user_id"
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
_IDENTITY_STATUS_UPDATE_SQL = (
    "UPDATE line_identity_bindings SET binding_status=%s,aggregate_version=%s "
    "WHERE line_user_id=%s AND aggregate_version=%s"
)
_IDENTITY_EVENT_SELECT_SQL = (
    "SELECT line_user_id,payload_fingerprint FROM line_identity_binding_events "
    "WHERE idempotency_key=%s"
)
_IDENTITY_TRANSITION_EVENT_INSERT_SQL = (
    "INSERT INTO line_identity_binding_events (line_user_id,action,subject_type,"
    "subject_reference,expected_version,resulting_version,actor_id,"
    "payload_fingerprint,idempotency_key,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_IDENTITY_EVENT_INSERT_SQL = (
    "INSERT INTO line_identity_binding_events (line_user_id,action,subject_type,"
    "subject_reference,expected_version,resulting_version,actor_id,"
    "payload_fingerprint,idempotency_key,correlation_id) "
    "VALUES (%s,'claim_submitted',%s,%s,%s,%s,'line-platform',%s,%s,%s)"
)
_REVIEW_SELECT_SQL = (
    "SELECT id,review_type,review_status,aggregate_version,line_user_id,"
    "subject_type,subject_reference,request_fingerprint,"
    "CAST(evidence_snapshot AS CHAR) AS evidence_snapshot,assigned_admin_id,"
    "assigned_at_utc,due_at_utc,reassignment_count,reviewed_by_actor_id,"
    "decision_reason,reviewed_at_utc,created_at_utc "
    "FROM line_review_requests WHERE id=%s"
)
_REVIEW_LIST_SQL = (
    "SELECT id,review_type,review_status,aggregate_version,line_user_id,"
    "subject_type,subject_reference,request_fingerprint,"
    "CAST(evidence_snapshot AS CHAR) AS evidence_snapshot,assigned_admin_id,"
    "assigned_at_utc,due_at_utc,reassignment_count,reviewed_by_actor_id,"
    "decision_reason,reviewed_at_utc,created_at_utc FROM line_review_requests"
)
_REVIEW_SUMMARY_SQL = (
    "SELECT SUM(review_status='pending') AS pending_total,"
    "SUM(review_status='pending' AND review_type='staff_verification') AS staff_pending,"
    "SUM(review_status='pending' AND review_type='client_rebind') AS rebind_pending,"
    "SUM(review_status IN ('approved','rejected') AND reviewed_at_utc >= UTC_DATE()) "
    "AS processed_today,"
    "SUM(review_status='pending' AND created_at_utc < "
    "TIMESTAMPADD(HOUR,-%s,UTC_TIMESTAMP(6))) AS stale_pending "
    "FROM line_review_requests"
)
_REVIEW_SELECT_BY_FLOW_SQL = (
    _REVIEW_LIST_SQL + " WHERE identity_flow_id=%s LIMIT 1"
)
_REVIEW_INSERT_SQL = (
    "INSERT INTO line_review_requests (review_type,line_user_id,subject_type,"
    "subject_reference,request_fingerprint,evidence_snapshot,identity_flow_id,"
    "request_idempotency_key,request_correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
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

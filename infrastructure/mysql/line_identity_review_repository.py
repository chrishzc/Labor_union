"""MySQL adapters for canonical LINE identity bindings and human reviews."""

from __future__ import annotations

from typing import Any

from domains.line.identities import LineReviewRequestId, LineUserId
from domains.line.identity_binding import (
    LineIdentityBindingFailureStreak,
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
    LineIdentityClaim,
    transition_binding_status,
    reset_binding_failure_streak,
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

    def get(self, line_user_id: LineUserId, subject_type=None) -> LineIdentityBindingSnapshot | None:
        if subject_type is None:
            bindings = tuple(
                binding
                for binding in self.list_by_user(line_user_id)
                if binding.status is not LineIdentityBindingStatus.REVOKED
            )
            if not bindings:
                return None
            if len(bindings) == 1:
                return bindings[0]
            selected_role, _ = self.selected_role(line_user_id)
            if selected_role is None:
                raise RuntimeError("line_identity_role_selection_required")
            selected = tuple(
                binding for binding in bindings if binding.subject_type is selected_role
            )
            if len(selected) != 1:
                raise RuntimeError("line_identity_selected_role_stale")
            return selected[0]
        with self._connection.cursor() as cursor:
            cursor.execute(
                _IDENTITY_SELECT_BY_ROLE_SQL,
                (line_user_id.value, subject_type.value),
            )
            row = optional_row(cursor.fetchone())
        return None if row is None else _identity_snapshot(row)

    def list_by_user(self, line_user_id):
        with self._connection.cursor() as cursor:
            cursor.execute(_IDENTITY_LIST_BY_USER_SQL, (line_user_id.value,))
            rows = tuple(cursor.fetchall() or ())
        return tuple(_identity_snapshot(row) for row in rows)

    def selected_role(self, line_user_id):
        with self._connection.cursor() as cursor:
            cursor.execute(_IDENTITY_SELECTED_ROLE_SQL, (line_user_id.value,))
            row = optional_row(cursor.fetchone())
        if row is None:
            raise LookupError("line_platform_user_not_found")
        selected = row.get("selected_identity_role")
        return (
            LineBindingSubjectType(str(selected)) if selected is not None else None,
            ExpectedVersion(int(row["aggregate_version"])),
        )

    def select_role(self, line_user_id, subject_type, expected_version):
        if subject_type not in {
            LineBindingSubjectType.CUSTOMER,
            LineBindingSubjectType.STAFF,
        }:
            raise ValueError("line_identity_selected_role_invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                _IDENTITY_SELECT_BY_ROLE_SQL + " FOR UPDATE",
                (line_user_id.value, subject_type.value),
            )
            row = optional_row(cursor.fetchone())
            if row is None or _identity_snapshot(row).status is not LineIdentityBindingStatus.BOUND:
                raise RuntimeError("line_identity_selected_role_not_bound")
            cursor.execute(
                _IDENTITY_SELECTED_ROLE_UPDATE_SQL,
                (
                    subject_type.value,
                    expected_version.value + 1,
                    line_user_id.value,
                    expected_version.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_identity_selected_role_version_conflict")
        return ExpectedVersion(expected_version.value + 1)

    def get_failure_streak(self, line_user_id, *, lock=False):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _IDENTITY_FAILURE_STREAK_SELECT_SQL + (" FOR UPDATE" if lock else ""),
                (line_user_id.value,),
            )
            row = optional_row(cursor.fetchone())
        return None if row is None else _failure_streak_snapshot(row)

    def save_failure_streak(self, streak):
        expected_version = streak.version.value - 1
        with self._connection.cursor() as cursor:
            if expected_version == 0:
                cursor.execute(
                    _IDENTITY_FAILURE_STREAK_INSERT_SQL,
                    _failure_streak_parameters(streak),
                )
                return
            cursor.execute(
                _IDENTITY_FAILURE_STREAK_UPDATE_SQL,
                (
                    streak.identity_flow_id,
                    streak.candidate_subject_type.value,
                    streak.candidate_scope,
                    streak.scope_fingerprint,
                    streak.generation,
                    streak.failure_count,
                    streak.last_failure_fingerprint,
                    streak.escalation_id,
                    streak.version.value,
                    streak.line_user_id.value,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_identity_failure_streak_version_conflict")

    def reset_failure_streak(self, line_user_id, identity_flow_id):
        current = self.get_failure_streak(line_user_id, lock=True)
        reset = reset_binding_failure_streak(current, identity_flow_id.value)
        if reset is not None:
            self.save_failure_streak(reset)

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
            self._lock_role_scope(cursor, claim)
            cursor.execute(
                _IDENTITY_SELECT_BY_ROLE_SQL + " FOR UPDATE",
                (claim.line_user_id.value, claim.subject_type.value),
            )
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
        subject_type=None,
    ):
        return self._transition_status(
            line_user_id,
            expected_version,
            LineIdentityBindingStatus.REVOKED,
            "revoked",
            actor_id,
            idempotency_key,
            correlation_id,
            subject_type,
        )

    def request_revocation(
        self,
        line_user_id,
        expected_version,
        actor_id,
        idempotency_key,
        correlation_id,
        subject_type=None,
    ):
        return self._transition_status(
            line_user_id,
            expected_version,
            LineIdentityBindingStatus.REVOCATION_PENDING,
            "revocation_requested",
            actor_id,
            idempotency_key,
            correlation_id,
            subject_type,
        )

    def complete_revocation(
        self,
        line_user_id,
        expected_version,
        actor_id,
        idempotency_key,
        correlation_id,
        subject_type=None,
    ):
        return self._transition_status(
            line_user_id,
            expected_version,
            LineIdentityBindingStatus.REVOKED,
            "revoked",
            actor_id,
            idempotency_key,
            correlation_id,
            subject_type,
        )

    # Kept cohesive because subject correction must preserve one locked aggregate event.
    def replace_subject(
        self,
        claim,
        expected_version,
        actor_id,
        idempotency_key,
        correlation_id,
    ):
        with self._connection.cursor() as cursor:
            existing = self._existing_event(cursor, idempotency_key.value)
            if existing is not None:
                snapshot = self.get(claim.line_user_id, claim.subject_type)
                if snapshot is None:
                    raise RuntimeError("line_identity_binding_missing")
                replay = LineIdentityBindingSnapshot(
                    claim.line_user_id,
                    snapshot.status,
                    snapshot.version,
                    claim.subject_type,
                    claim.subject_reference,
                )
                _require_same_transition_event(
                    existing,
                    replay,
                    LineIdentityBindingStatus.BOUND,
                    "rebound",
                    actor_id,
                )
                return snapshot
            self._lock_role_scope(cursor, claim)
            cursor.execute(
                _IDENTITY_SELECT_BY_ROLE_SQL + " FOR UPDATE",
                (claim.line_user_id.value, claim.subject_type.value),
            )
            row = optional_row(cursor.fetchone())
            if row is None:
                raise LookupError("line_identity_binding_not_found")
            current = _identity_snapshot(row)
            _require_replaceable_binding(current, claim, expected_version)
            resulting_version = expected_version.value + 1
            cursor.execute(
                _IDENTITY_UPDATE_SQL,
                (
                    LineIdentityBindingStatus.BOUND.value,
                    claim.subject_reference,
                    resulting_version,
                    claim.line_user_id.value,
                    claim.subject_type.value,
                    expected_version.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_identity_binding_conflict")
            resulting = LineIdentityBindingSnapshot(
                claim.line_user_id,
                LineIdentityBindingStatus.BOUND,
                ExpectedVersion(resulting_version),
                claim.subject_type,
                claim.subject_reference,
            )
            self._append_transition_event(
                cursor,
                LineIdentityBindingSnapshot(
                    current.line_user_id,
                    current.status,
                    current.version,
                    claim.subject_type,
                    claim.subject_reference,
                ),
                LineIdentityBindingStatus.BOUND,
                "rebound",
                actor_id,
                idempotency_key.value,
                correlation_id,
            )
        return resulting

    # Kept cohesive because replay validation, row lock, transition, and event are atomic.
    def _transition_status(
        self,
        line_user_id,
        expected_version,
        target,
        action,
        actor_id,
        idempotency_key,
        correlation_id,
        subject_type=None,
    ):
        resolved_type = subject_type
        if resolved_type is None:
            current = self.get(line_user_id)
            if current is None or current.subject_type is None:
                raise LookupError("line_identity_binding_not_found")
            resolved_type = current.subject_type
        with self._connection.cursor() as cursor:
            existing = self._existing_event(cursor, idempotency_key.value)
            if existing is not None:
                snapshot = self.get(line_user_id, resolved_type)
                if snapshot is None:
                    raise RuntimeError("line_identity_binding_missing")
                _require_same_transition_event(
                    existing,
                    snapshot,
                    target,
                    action,
                    actor_id,
                )
                return snapshot
            cursor.execute(
                _IDENTITY_SELECT_BY_ROLE_SQL + " FOR UPDATE",
                (line_user_id.value, resolved_type.value),
            )
            row = optional_row(cursor.fetchone())
            if row is None:
                raise LookupError("line_identity_binding_not_found")
            snapshot = _identity_snapshot(row)
            if snapshot.status is target:
                return snapshot
            if snapshot.version != expected_version:
                raise RuntimeError("line_identity_binding_conflict")
            transition_binding_status(snapshot.status, target)
            resulting_version = expected_version.value + 1
            cursor.execute(
                _IDENTITY_STATUS_UPDATE_SQL,
                (
                    target.value,
                    resulting_version,
                    line_user_id.value,
                    resolved_type.value,
                    expected_version.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_identity_binding_conflict")
            self._append_transition_event(
                cursor,
                snapshot,
                target,
                action,
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
                snapshot = self.get(claim.line_user_id, claim.subject_type)
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
            self._lock_role_scope(cursor, claim)
            cursor.execute(
                _IDENTITY_SELECT_BY_ROLE_SQL + " FOR UPDATE",
                (claim.line_user_id.value, claim.subject_type.value),
            )
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

    def _lock_role_scope(self, cursor, claim):
        cursor.execute(
            _IDENTITY_ROLE_SCOPE_LOCK_SQL,
            (claim.line_user_id.value,),
        )
        if optional_row(cursor.fetchone()) is None:
            raise LookupError("line_platform_user_not_found")
        cursor.execute(
            _IDENTITY_ROLE_SCOPE_COUNTS_SQL,
            (claim.line_user_id.value,),
        )
        counts = optional_row(cursor.fetchone()) or {}
        admin_count = int(counts.get("admin_count") or 0)
        nonadmin_count = int(counts.get("nonadmin_count") or 0)
        if claim.subject_type is LineBindingSubjectType.ADMIN and nonadmin_count:
            raise RuntimeError("line_identity_admin_role_exclusive")
        if claim.subject_type is not LineBindingSubjectType.ADMIN and admin_count:
            raise RuntimeError("line_identity_admin_role_exclusive")

    def _persist_binding_transition(self, cursor, snapshot, claim, target, version, is_new):
        if is_new:
            cursor.execute(
                _IDENTITY_INSERT_SQL,
                (claim.line_user_id.value, target.value, claim.subject_type.value, claim.subject_reference, version),
            )
            return
        cursor.execute(
            _IDENTITY_UPDATE_SQL,
            (
                target.value,
                claim.subject_reference,
                version,
                claim.line_user_id.value,
                claim.subject_type.value,
                snapshot.version.value,
            ),
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
                    claim.subject_reference,
                    resulting_version,
                    claim.line_user_id.value,
                    claim.subject_type.value,
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
        if query.page is not None:
            return self._list_numbered_page(query)
        sql, parameters = _review_list_statement(query)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            rows = tuple(cursor.fetchall() or ())
        has_more = len(rows) > query.page_size
        visible_rows = rows[: query.page_size]
        items = tuple(_review_snapshot(row) for row in visible_rows)
        next_cursor = str(visible_rows[-1]["id"]) if has_more else None
        return LineReviewPage(items, next_cursor)

    def _list_numbered_page(self, query: LineReviewListQuery) -> LineReviewPage:
        count_sql, count_parameters = _review_count_statement(query)
        page_sql, page_parameters = _review_numbered_page_statement(query)
        with self._connection.cursor() as cursor:
            cursor.execute(count_sql, count_parameters)
            count_row = optional_row(cursor.fetchone()) or {}
            cursor.execute(page_sql, page_parameters)
            rows = tuple(cursor.fetchall() or ())
        return LineReviewPage(
            tuple(_review_snapshot(row) for row in rows),
            None,
            query.page,
            query.page_size,
            int(count_row.get("total") or 0),
        )

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


def _require_replaceable_binding(snapshot, claim, expected_version):
    if snapshot.status is not LineIdentityBindingStatus.BOUND:
        raise RuntimeError("line_identity_binding_not_bound")
    if snapshot.version != expected_version:
        raise RuntimeError("line_identity_binding_conflict")
    if snapshot.subject_type is not claim.subject_type:
        raise RuntimeError("line_identity_subject_type_change_forbidden")
    if snapshot.subject_reference == claim.subject_reference:
        raise RuntimeError("line_identity_subject_unchanged")


def _identity_snapshot(row):
    subject_type = row.get("subject_type")
    return LineIdentityBindingSnapshot(
        LineUserId(str(row["line_user_id"])),
        LineIdentityBindingStatus(str(row["binding_status"])),
        ExpectedVersion(int(row["aggregate_version"])),
        LineBindingSubjectType(str(subject_type)) if subject_type is not None else None,
        _optional_text(row.get("subject_reference")),
    )


def _failure_streak_snapshot(row):
    return LineIdentityBindingFailureStreak(
        LineUserId(str(row["line_user_id"])),
        str(row["identity_flow_id"]),
        LineBindingSubjectType(str(row["candidate_subject_type"])),
        str(row["candidate_scope"]),
        str(row["scope_fingerprint"]),
        int(row["streak_generation"]),
        int(row["failure_count"]),
        _optional_text(row.get("last_failure_fingerprint")),
        int(row["escalation_id"]) if row.get("escalation_id") is not None else None,
        ExpectedVersion(int(row["aggregate_version"])),
    )


def _failure_streak_parameters(streak):
    return (
        streak.line_user_id.value,
        streak.identity_flow_id,
        streak.candidate_subject_type.value,
        streak.candidate_scope,
        streak.scope_fingerprint,
        streak.generation,
        streak.failure_count,
        streak.last_failure_fingerprint,
        streak.escalation_id,
        streak.version.value,
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
    clauses, parameters = _review_filter_parts(query)
    if query.cursor is not None:
        clauses.append("id < %s")
        parameters.append(int(query.cursor))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    parameters.append(query.page_size + 1)
    return _REVIEW_LIST_SQL + where + " ORDER BY id DESC LIMIT %s", tuple(parameters)


def _review_count_statement(query):
    clauses, parameters = _review_filter_parts(query)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return "SELECT COUNT(*) AS total FROM line_review_requests" + where, tuple(parameters)


def _review_numbered_page_statement(query):
    clauses, parameters = _review_filter_parts(query)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    parameters.extend((query.page_size, (query.page - 1) * query.page_size))
    return _REVIEW_LIST_SQL + where + " ORDER BY id DESC LIMIT %s OFFSET %s", tuple(parameters)


def _review_filter_parts(query):
    clauses = []
    parameters: list[object] = []
    if query.statuses:
        clauses.append("review_status IN (" + ",".join(["%s"] * len(query.statuses)) + ")")
        parameters.extend(item.value for item in query.statuses)
    if query.review_types:
        clauses.append("review_type IN (" + ",".join(["%s"] * len(query.review_types)) + ")")
        parameters.extend(item.value for item in query.review_types)
    return clauses, parameters


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


_IDENTITY_SELECT_BY_ROLE_SQL = (
    "SELECT line_user_id,binding_status,subject_type,subject_reference,"
    "aggregate_version FROM line_identity_role_bindings "
    "WHERE line_user_id=%s AND subject_type=%s"
)
_IDENTITY_LIST_BY_USER_SQL = (
    "SELECT line_user_id,binding_status,subject_type,subject_reference,"
    "aggregate_version FROM line_identity_role_bindings WHERE line_user_id=%s "
    "ORDER BY subject_type"
)
_IDENTITY_SELECT_BY_SUBJECT_SQL = (
    "SELECT line_user_id,binding_status,subject_type,subject_reference,"
    "aggregate_version FROM line_identity_role_bindings "
    "WHERE subject_type=%s AND subject_reference=%s "
    "AND binding_status IN ('pending_review','bound') LIMIT 1"
)
_IDENTITY_LIST_BOUND_SQL = (
    "SELECT line_user_id,binding_status,subject_type,subject_reference,"
    "aggregate_version FROM line_identity_role_bindings "
    "WHERE subject_type=%s AND binding_status='bound' ORDER BY line_user_id"
)
_IDENTITY_INSERT_SQL = (
    "INSERT INTO line_identity_role_bindings (line_user_id,binding_status,subject_type,"
    "subject_reference,aggregate_version) VALUES (%s,%s,%s,%s,%s)"
)
_IDENTITY_UPDATE_SQL = (
    "UPDATE line_identity_role_bindings SET binding_status=%s,"
    "subject_reference=%s,aggregate_version=%s WHERE line_user_id=%s "
    "AND subject_type=%s AND aggregate_version=%s"
)
_IDENTITY_STATUS_UPDATE_SQL = (
    "UPDATE line_identity_role_bindings SET binding_status=%s,aggregate_version=%s "
    "WHERE line_user_id=%s AND subject_type=%s AND aggregate_version=%s"
)
_IDENTITY_EVENT_SELECT_SQL = (
    "SELECT line_user_id,payload_fingerprint FROM line_identity_role_binding_events "
    "WHERE idempotency_key=%s"
)
_IDENTITY_TRANSITION_EVENT_INSERT_SQL = (
    "INSERT INTO line_identity_role_binding_events (line_user_id,action,subject_type,"
    "subject_reference,expected_version,resulting_version,actor_id,"
    "payload_fingerprint,idempotency_key,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_IDENTITY_EVENT_INSERT_SQL = (
    "INSERT INTO line_identity_role_binding_events (line_user_id,action,subject_type,"
    "subject_reference,expected_version,resulting_version,actor_id,"
    "payload_fingerprint,idempotency_key,correlation_id) "
    "VALUES (%s,'claim_submitted',%s,%s,%s,%s,'line-platform',%s,%s,%s)"
)
_IDENTITY_SELECTED_ROLE_SQL = (
    "SELECT selected_identity_role,aggregate_version FROM line_platform_users "
    "WHERE line_user_id=%s"
)
_IDENTITY_SELECTED_ROLE_UPDATE_SQL = (
    "UPDATE line_platform_users SET selected_identity_role=%s,aggregate_version=%s "
    "WHERE line_user_id=%s AND aggregate_version=%s"
)
_IDENTITY_ROLE_SCOPE_LOCK_SQL = (
    "SELECT line_user_id FROM line_platform_users WHERE line_user_id=%s FOR UPDATE"
)
_IDENTITY_ROLE_SCOPE_COUNTS_SQL = (
    "SELECT SUM(subject_type='admin' AND binding_status IN "
    "('pending_review','bound','revocation_pending')) AS admin_count,"
    "SUM(subject_type IN ('customer','staff') AND binding_status IN "
    "('pending_review','bound','revocation_pending')) AS nonadmin_count "
    "FROM line_identity_role_bindings WHERE line_user_id=%s"
)
_IDENTITY_FAILURE_STREAK_SELECT_SQL = (
    "SELECT line_user_id,identity_flow_id,candidate_subject_type,"
    "candidate_scope,scope_fingerprint,streak_generation,"
    "failure_count,last_failure_fingerprint,escalation_id,aggregate_version "
    "FROM line_identity_binding_failure_streaks WHERE line_user_id=%s"
)
_IDENTITY_FAILURE_STREAK_INSERT_SQL = (
    "INSERT INTO line_identity_binding_failure_streaks "
    "(line_user_id,identity_flow_id,candidate_subject_type,"
    "candidate_scope,scope_fingerprint,streak_generation,"
    "failure_count,last_failure_fingerprint,escalation_id,aggregate_version) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_IDENTITY_FAILURE_STREAK_UPDATE_SQL = (
    "UPDATE line_identity_binding_failure_streaks SET identity_flow_id=%s,"
    "candidate_subject_type=%s,candidate_scope=%s,scope_fingerprint=%s,"
    "streak_generation=%s,failure_count=%s,last_failure_fingerprint=%s,"
    "escalation_id=%s,aggregate_version=%s WHERE line_user_id=%s "
    "AND aggregate_version=%s"
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

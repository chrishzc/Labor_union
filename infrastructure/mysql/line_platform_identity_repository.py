"""
File: line_platform_identity_repository.py
Description: 保存 verified platform user、friend events 與 one-use LIFF identity flows。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from domains.line.identities import LineIdentityFlowId, LineUserId
from domains.line.identity_flow import (
    LineIdentityFlowPurpose,
    LineIdentityFlowSnapshot,
    LineIdentityFlowStatus,
    validate_identity_flow,
)
from domains.line.platform_user import (
    LineFriendEvent,
    LineFriendEventType,
    LineFriendStatus,
    LinePlatformUserSnapshot,
    friend_status_for_event,
)
from infrastructure.mysql.line_repository_support import aware_utc, database_utc, optional_row
from shared_kernel.identities import ExpectedVersion
from subsystems.line.identity_contracts import (
    LineIdentityCommandOutcome,
    OpenLineIdentityFlowCommand,
    OpenLineIdentityFlowResult,
)


class MySqlLinePlatformUserRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, line_user_id: LineUserId) -> LinePlatformUserSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_PLATFORM_USER_SELECT_SQL, (line_user_id.value,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _platform_user_snapshot(row)

    def ensure_verified_user(self, line_user_id: LineUserId) -> LinePlatformUserSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_PLATFORM_USER_ENSURE_VERIFIED_SQL, (line_user_id.value,))
            cursor.execute(_PLATFORM_USER_SELECT_SQL, (line_user_id.value,))
            row = optional_row(cursor.fetchone())
        if row is None:
            raise RuntimeError("line_platform_user_observation_failed")
        return _platform_user_snapshot(row)

    def apply_friend_event(self, event: LineFriendEvent) -> LinePlatformUserSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_FRIEND_EVENT_SELECT_SQL, (event.event_id.value,))
            existing = optional_row(cursor.fetchone())
            if existing is not None:
                _require_same_friend_event(existing, event)
                snapshot = self.get(event.line_user_id)
                if snapshot is None:
                    raise RuntimeError("line_platform_user_missing")
                return snapshot
            snapshot = self._locked_or_initial(cursor, event.line_user_id)
            resulting = _friend_event_result(snapshot, event)
            self._persist_friend_event(cursor, snapshot, resulting, event)
            _update_legacy_line_user_projection(cursor, event)
        return resulting

    def _locked_or_initial(self, cursor, line_user_id):
        cursor.execute(_PLATFORM_USER_SELECT_SQL + " FOR UPDATE", (line_user_id.value,))
        row = optional_row(cursor.fetchone())
        if row is not None:
            return _platform_user_snapshot(row)
        return LinePlatformUserSnapshot(
            line_user_id,
            LineFriendStatus.UNKNOWN,
            ExpectedVersion(0),
        )

    # Kept cohesive so projection and immutable friend event advance one version together.
    def _persist_friend_event(self, cursor, before, after, event):
        if before.version.value == 0:
            cursor.execute(_PLATFORM_USER_INSERT_SQL, _platform_user_values(after))
        else:
            cursor.execute(
                _PLATFORM_USER_UPDATE_SQL,
                (*_platform_user_update_values(after), event.line_user_id.value, before.version.value),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_platform_user_version_conflict")
        cursor.execute(
            _FRIEND_EVENT_INSERT_SQL,
            (
                event.event_id.value,
                event.line_user_id.value,
                event.event_type.value,
                before.friend_status.value,
                after.friend_status.value,
                before.version.value,
                after.version.value,
                database_utc(event.occurred_at),
            ),
        )


class MySqlLineIdentityFlowRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    # Kept cohesive because idempotent replay and flow creation share one unique key.
    def open(self, command: OpenLineIdentityFlowCommand) -> OpenLineIdentityFlowResult:
        with self._connection.cursor() as cursor:
            cursor.execute(_FLOW_SELECT_BY_KEY_SQL, (command.idempotency_key.value,))
            existing = optional_row(cursor.fetchone())
            if existing is not None:
                _require_same_flow(existing, command)
                return _open_flow_result(existing, LineIdentityCommandOutcome.EXISTING)
            flow_id = LineIdentityFlowId(str(uuid4()))
            cursor.execute(
                _FLOW_INSERT_SQL,
                (
                    flow_id.value,
                    command.purpose.value,
                    command.line_user_id.value,
                    database_utc(command.expires_at),
                    command.idempotency_key.value,
                    command.correlation_id.value,
                ),
            )
        return OpenLineIdentityFlowResult(
            flow_id,
            command.purpose,
            command.line_user_id,
            command.expires_at,
            LineIdentityCommandOutcome.CREATED,
        )

    def get(self, flow_id: LineIdentityFlowId) -> LineIdentityFlowSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_FLOW_SELECT_SQL, (flow_id.value,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _flow_snapshot(row)

    # Kept cohesive because validation and one-use consumption must hold the same lock.
    def consume(self, flow_id, purpose, line_user_id, now):
        with self._connection.cursor() as cursor:
            cursor.execute(_FLOW_SELECT_SQL + " FOR UPDATE", (flow_id.value,))
            row = optional_row(cursor.fetchone())
            if row is None:
                raise LookupError("line_identity_flow_not_found")
            snapshot = _flow_snapshot(row)
            validate_identity_flow(
                snapshot,
                purpose=purpose,
                line_user_id=line_user_id,
                now=now,
            )
            cursor.execute(
                _FLOW_CONSUME_SQL,
                (database_utc(now), flow_id.value),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_identity_flow_conflict")
        return LineIdentityFlowSnapshot(
            flow_id,
            purpose,
            line_user_id,
            LineIdentityFlowStatus.USED,
            snapshot.expires_at,
            snapshot.idempotency_key,
            snapshot.attempt_count + 1,
        )

    # Kept cohesive because attempt increment and cancellation threshold are one transition.
    def record_failed_attempt(self, flow_id, maximum_attempts):
        if maximum_attempts < 1:
            raise ValueError("LINE identity flow maximum attempts must be positive")
        with self._connection.cursor() as cursor:
            cursor.execute(_FLOW_SELECT_SQL + " FOR UPDATE", (flow_id.value,))
            row = optional_row(cursor.fetchone())
            if row is None:
                raise LookupError("line_identity_flow_not_found")
            snapshot = _flow_snapshot(row)
            if snapshot.status is not LineIdentityFlowStatus.ACTIVE:
                return snapshot
            attempts = snapshot.attempt_count + 1
            status = "cancelled" if attempts >= maximum_attempts else "active"
            cursor.execute(_FLOW_ATTEMPT_SQL, (attempts, status, flow_id.value))
        return LineIdentityFlowSnapshot(
            snapshot.flow_id,
            snapshot.purpose,
            snapshot.line_user_id,
            LineIdentityFlowStatus(status),
            snapshot.expires_at,
            snapshot.idempotency_key,
            attempts,
        )


def _friend_event_result(snapshot, event):
    followed_at = event.occurred_at if event.event_type is LineFriendEventType.FOLLOW else None
    return LinePlatformUserSnapshot(
        event.line_user_id,
        friend_status_for_event(event.event_type),
        ExpectedVersion(snapshot.version.value + 1),
        snapshot.first_followed_at or followed_at,
        followed_at or snapshot.last_followed_at,
        event.occurred_at if event.event_type is LineFriendEventType.UNFOLLOW else None,
        event.occurred_at,
    )


def _require_same_friend_event(existing, event):
    if str(existing["line_user_id"]) != event.line_user_id.value:
        raise RuntimeError("line_friend_event_idempotency_conflict")
    if str(existing["event_type"]) != event.event_type.value:
        raise RuntimeError("line_friend_event_idempotency_conflict")


def _require_same_flow(existing, command):
    if str(existing["flow_purpose"]) != command.purpose.value:
        raise RuntimeError("line_identity_flow_idempotency_conflict")
    if str(existing["line_user_id"]) != command.line_user_id.value:
        raise RuntimeError("line_identity_flow_idempotency_conflict")


def _platform_user_snapshot(row):
    return LinePlatformUserSnapshot(
        LineUserId(str(row["line_user_id"])),
        LineFriendStatus(str(row["friend_status"])),
        ExpectedVersion(int(row["aggregate_version"])),
        _aware_optional(row.get("first_followed_at_utc")),
        _aware_optional(row.get("last_followed_at_utc")),
        _aware_optional(row.get("blocked_at_utc")),
        _aware_optional(row.get("last_event_at_utc")),
    )


def _platform_user_values(snapshot):
    return (
        snapshot.line_user_id.value,
        snapshot.friend_status.value,
        _database_optional(snapshot.first_followed_at),
        _database_optional(snapshot.last_followed_at),
        _database_optional(snapshot.blocked_at),
        _database_optional(snapshot.last_event_at),
        snapshot.version.value,
    )


def _platform_user_update_values(snapshot):
    return _platform_user_values(snapshot)[1:]


def _update_legacy_line_user_projection(cursor, event):
    status = "blocked" if event.event_type is LineFriendEventType.UNFOLLOW else "active"
    cursor.execute(
        _LEGACY_LINE_USER_UPSERT_SQL,
        (
            event.line_user_id.value,
            status,
            database_utc(event.occurred_at) if status == "active" else None,
            database_utc(event.occurred_at) if status == "blocked" else None,
            database_utc(event.occurred_at),
        ),
    )


def _flow_snapshot(row):
    return LineIdentityFlowSnapshot(
        LineIdentityFlowId(str(row["flow_id"])),
        LineIdentityFlowPurpose(str(row["flow_purpose"])),
        LineUserId(str(row["line_user_id"])),
        LineIdentityFlowStatus(str(row["flow_status"])),
        aware_utc(row["expires_at_utc"]),
        str(row["idempotency_key"]),
        int(row.get("attempt_count") or 0),
    )


def _open_flow_result(row, outcome):
    snapshot = _flow_snapshot(row)
    return OpenLineIdentityFlowResult(
        snapshot.flow_id,
        snapshot.purpose,
        snapshot.line_user_id,
        snapshot.expires_at,
        outcome,
    )


def _aware_optional(value):
    return None if value is None else aware_utc(value)


def _database_optional(value):
    return None if value is None else database_utc(value)


_PLATFORM_USER_SELECT_SQL = (
    "SELECT line_user_id,friend_status,first_followed_at_utc,last_followed_at_utc,"
    "blocked_at_utc,last_event_at_utc,aggregate_version FROM line_platform_users "
    "WHERE line_user_id=%s"
)
_PLATFORM_USER_ENSURE_VERIFIED_SQL = (
    "INSERT IGNORE INTO line_platform_users (line_user_id) VALUES (%s)"
)
_PLATFORM_USER_INSERT_SQL = (
    "INSERT INTO line_platform_users (line_user_id,friend_status,first_followed_at_utc,"
    "last_followed_at_utc,blocked_at_utc,last_event_at_utc,aggregate_version) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE friend_status=VALUES(friend_status),"
    "first_followed_at_utc=VALUES(first_followed_at_utc),"
    "last_followed_at_utc=VALUES(last_followed_at_utc),"
    "blocked_at_utc=VALUES(blocked_at_utc),"
    "last_event_at_utc=VALUES(last_event_at_utc),"
    "aggregate_version=VALUES(aggregate_version)"
)
_PLATFORM_USER_UPDATE_SQL = (
    "UPDATE line_platform_users SET friend_status=%s,first_followed_at_utc=%s,"
    "last_followed_at_utc=%s,blocked_at_utc=%s,last_event_at_utc=%s,"
    "aggregate_version=%s WHERE line_user_id=%s AND aggregate_version=%s"
)
_FRIEND_EVENT_SELECT_SQL = (
    "SELECT event_identity,line_user_id,event_type FROM line_friend_state_events "
    "WHERE event_identity=%s"
)
_FRIEND_EVENT_INSERT_SQL = (
    "INSERT INTO line_friend_state_events (event_identity,line_user_id,event_type,"
    "before_status,after_status,expected_version,resulting_version,occurred_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
)
_FLOW_SELECT_COLUMNS = (
    "flow_id,flow_purpose,line_user_id,flow_status,expires_at_utc,idempotency_key,"
    "attempt_count"
)
_FLOW_SELECT_SQL = (
    f"SELECT {_FLOW_SELECT_COLUMNS} FROM line_identity_flows WHERE flow_id=%s"
)
_FLOW_SELECT_BY_KEY_SQL = (
    f"SELECT {_FLOW_SELECT_COLUMNS} FROM line_identity_flows WHERE idempotency_key=%s"
)
_FLOW_INSERT_SQL = (
    "INSERT INTO line_identity_flows (flow_id,flow_purpose,line_user_id,expires_at_utc,"
    "idempotency_key,correlation_id) VALUES (%s,%s,%s,%s,%s,%s)"
)
_FLOW_CONSUME_SQL = (
    "UPDATE line_identity_flows SET flow_status='used',used_at_utc=%s,attempt_count="
    "attempt_count+1 WHERE flow_id=%s AND flow_status='active'"
)
_FLOW_ATTEMPT_SQL = (
    "UPDATE line_identity_flows SET attempt_count=%s,flow_status=%s WHERE flow_id=%s"
)
_LEGACY_LINE_USER_UPSERT_SQL = (
    "INSERT INTO line_users (line_user_id,status,followed_at,blocked_at,last_event_at) "
    "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE status=VALUES(status),"
    "followed_at=COALESCE(VALUES(followed_at),followed_at),blocked_at=VALUES(blocked_at),"
    "last_event_at=VALUES(last_event_at)"
)


__all__ = [
    "MySqlLineIdentityFlowRepository",
    "MySqlLinePlatformUserRepository",
]

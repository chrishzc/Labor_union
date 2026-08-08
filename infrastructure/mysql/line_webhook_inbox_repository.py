"""MySQL adapter for canonical LINE webhook inbox registration and transitions."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pymysql.err import IntegrityError

from domains.line.identities import (
    LineDestinationId,
    LineWebhookEventId,
)
from domains.line.webhook import (
    CanonicalLineWebhookEvent,
    LineWebhookInboxSnapshot,
    LineWebhookLease,
    LineWebhookProcessingStatus,
    transition_webhook_status,
)
from infrastructure.mysql.line_repository_support import (
    aware_utc,
    canonical_json_value,
    database_utc,
    mysql_error_code,
    optional_row,
    source_identity,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ExpectedVersion
from subsystems.line.webhook_contracts import (
    AcceptLineWebhookEventResult,
    ClaimLineWebhookEventsQuery,
    CompleteLineWebhookEventCommand,
    LineWebhookRegistrationOutcome,
)


class MySqlLineWebhookInboxRepository:
    def __init__(self, connection: Any, *, lease_duration_seconds: int = 60) -> None:
        self._connection = connection
        self._lease_duration = timedelta(seconds=lease_duration_seconds)

    def register(
        self,
        event: CanonicalLineWebhookEvent,
    ) -> AcceptLineWebhookEventResult:
        try:
            event_row_id = self._insert(event)
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            return self._existing_registration(event)
        return AcceptLineWebhookEventResult(
            LineWebhookRegistrationOutcome.CREATED,
            LineWebhookEventId(event.event_id.value),
            LineWebhookProcessingStatus.PENDING,
            ExpectedVersion(0),
        )

    def get(self, event_id: LineWebhookEventId) -> LineWebhookInboxSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_SELECT_SQL, (event_id.value,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _snapshot(row)

    def transition(
        self,
        event_id: LineWebhookEventId,
        expected_version: ExpectedVersion,
        target_status: LineWebhookProcessingStatus,
    ) -> LineWebhookInboxSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_SELECT_SQL + " FOR UPDATE", (event_id.value,))
            row = optional_row(cursor.fetchone())
            if row is None:
                raise LookupError("line_webhook_event_not_found")
            current = LineWebhookProcessingStatus(str(row["processing_status"]))
            transition_webhook_status(current, target_status)
            cursor.execute(
                _TRANSITION_SQL,
                (
                    target_status.value,
                    target_status.value,
                    event_id.value,
                    expected_version.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_webhook_version_conflict")
            cursor.execute(_SELECT_SQL, (event_id.value,))
            updated = cursor.fetchone()
        return _snapshot(updated)

    def claim(
        self,
        query: ClaimLineWebhookEventsQuery,
    ) -> tuple[LineWebhookInboxSnapshot, ...]:
        lease_expires_at = query.now + self._lease_duration
        with self._connection.cursor() as cursor:
            database_now = database_utc(query.now)
            cursor.execute(_EXHAUSTED_UPDATE_SQL, (database_now, database_now))
            cursor.execute(
                _CLAIM_CANDIDATES_SQL,
                (
                    database_utc(query.now),
                    database_utc(query.now),
                    database_utc(query.now),
                    query.batch_size,
                ),
            )
            rows = tuple(cursor.fetchall() or ())
            event_ids = tuple(str(row["event_identity"]) for row in rows)
            for event_id in event_ids:
                cursor.execute(
                    _CLAIM_UPDATE_SQL,
                    (
                        query.lease_owner,
                        database_utc(query.now),
                        database_utc(lease_expires_at),
                        event_id,
                    ),
                )
            claimed = tuple(self._load_rows(cursor, event_ids))
        return tuple(_snapshot(row) for row in claimed)

    def complete(
        self,
        command: CompleteLineWebhookEventCommand,
    ) -> LineWebhookInboxSnapshot:
        next_attempt_at = _next_attempt_at(command)
        with self._connection.cursor() as cursor:
            cursor.execute(_SELECT_SQL + " FOR UPDATE", (command.event.event.event_id.value,))
            row = optional_row(cursor.fetchone())
            if row is None:
                raise LookupError("line_webhook_event_not_found")
            _require_matching_lease(row, command)
            cursor.execute(
                _COMPLETE_SQL,
                (
                    command.target_status.value,
                    database_utc(next_attempt_at) if next_attempt_at else None,
                    command.error_code,
                    command.error_message,
                    _processed_at(command),
                    command.event.event.event_id.value,
                    command.lease.owner,
                    command.event.version.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_webhook_lease_lost")
            cursor.execute(_SELECT_SQL, (command.event.event.event_id.value,))
            updated = cursor.fetchone()
        return _snapshot(updated)

    def next_due_at(self):
        with self._connection.cursor() as cursor:
            cursor.execute(_NEXT_DUE_SQL)
            row = optional_row(cursor.fetchone())
        due_at = None if row is None else row.get("next_due_at_utc")
        return aware_utc(due_at) if due_at is not None else None

    def _load_rows(self, cursor: Any, event_ids: tuple[str, ...]):
        for event_id in event_ids:
            cursor.execute(_SELECT_SQL, (event_id,))
            row = optional_row(cursor.fetchone())
            if row is not None:
                yield row

    def _insert(self, event: CanonicalLineWebhookEvent) -> int:
        source = event.source
        with self._connection.cursor() as cursor:
            cursor.execute(
                _INSERT_SQL,
                (
                    event.event_id.value,
                    event.event_id.value if event.uses_provider_event_id else None,
                    event.destination_id.value,
                    event.event_type,
                    source.source_type.value,
                    source.source_id,
                    source.user_id.value if source.user_id else None,
                    database_utc(event.occurred_at),
                    event.payload_fingerprint.value,
                    event.payload_json,
                    "provider" if event.uses_provider_event_id else "fingerprint",
                    event.is_redelivery,
                ),
            )
            return int(cursor.lastrowid)

    def _existing_registration(
        self,
        event: CanonicalLineWebhookEvent,
    ) -> AcceptLineWebhookEventResult:
        snapshot = self.get(event.event_id)
        if snapshot is None:
            raise RuntimeError("line_webhook_duplicate_missing")
        if snapshot.event.payload_fingerprint != event.payload_fingerprint:
            raise RuntimeError("line_webhook_idempotency_conflict")
        return AcceptLineWebhookEventResult(
            LineWebhookRegistrationOutcome.EXISTING,
            snapshot.event.event_id,
            snapshot.status,
            snapshot.version,
        )


def _snapshot(row: object) -> LineWebhookInboxSnapshot:
    if not isinstance(row, dict):
        row = dict(row)
    event = CanonicalLineWebhookEvent(
        event_id=LineWebhookEventId(str(row["event_identity"])),
        destination_id=LineDestinationId(str(row["destination_id"])),
        event_type=str(row["event_type"]),
        source=source_identity(
            str(row["source_type"]),
            str(row["source_identity"]),
            _optional_text(row.get("source_user_id")),
        ),
        occurred_at=aware_utc(row["occurred_at_utc"]),
        payload_fingerprint=PreviewFingerprint(str(row["payload_fingerprint"])),
        is_redelivery=bool(row["is_redelivery"]),
        uses_provider_event_id=str(row["identity_source"]) == "provider",
        payload_json=canonical_json_value(row["payload_snapshot"]),
    )
    return LineWebhookInboxSnapshot(
        event,
        LineWebhookProcessingStatus(str(row["processing_status"])),
        ExpectedVersion(int(row["aggregate_version"])),
        int(row.get("attempt_count", 0)),
        _lease(row, event.event_id),
        int(row.get("max_attempts", 5)),
    )


def _lease(row: dict[str, object], event_id: LineWebhookEventId):
    owner = _optional_text(row.get("lease_owner"))
    if owner is None:
        return None
    return LineWebhookLease(
        event_id,
        owner,
        aware_utc(row["lease_acquired_at_utc"]),
        aware_utc(row["lease_expires_at_utc"]),
    )


def _require_matching_lease(row, command: CompleteLineWebhookEventCommand) -> None:
    actual = (
        str(row["processing_status"]),
        _optional_text(row.get("lease_owner")),
        aware_utc(row["lease_acquired_at_utc"]),
        aware_utc(row["lease_expires_at_utc"]),
        int(row["aggregate_version"]),
    )
    expected = (
        LineWebhookProcessingStatus.PROCESSING.value,
        command.lease.owner,
        command.lease.acquired_at,
        command.lease.expires_at,
        command.event.version.value,
    )
    if actual != expected or command.completed_at > command.lease.expires_at:
        raise RuntimeError("line_webhook_lease_lost")


def _next_attempt_at(command: CompleteLineWebhookEventCommand):
    if command.target_status is not LineWebhookProcessingStatus.RETRYABLE_FAILED:
        return None
    delay = command.retry_after_seconds if command.retry_after_seconds is not None else 15
    return command.completed_at + timedelta(seconds=delay)


def _processed_at(command: CompleteLineWebhookEventCommand):
    if command.target_status is LineWebhookProcessingStatus.RETRYABLE_FAILED:
        return None
    return database_utc(command.completed_at)


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


_INSERT_SQL = (
    "INSERT INTO line_inbox_events (event_identity,provider_event_id,"
    "destination_id,event_type,source_type,source_identity,source_user_id,"
    "occurred_at_utc,payload_fingerprint,payload_snapshot,identity_source,"
    "is_redelivery) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_SELECT_SQL = (
    "SELECT event_identity,destination_id,event_type,source_type,source_identity,"
    "source_user_id,occurred_at_utc,payload_fingerprint,payload_snapshot,"
    "identity_source,is_redelivery,processing_status,aggregate_version,attempt_count,max_attempts,"
    "lease_owner,lease_acquired_at_utc,lease_expires_at_utc "
    "FROM line_inbox_events WHERE event_identity=%s"
)
_CLAIM_CANDIDATES_SQL = (
    _SELECT_SQL.replace(" WHERE event_identity=%s", "")
    + " WHERE attempt_count<max_attempts AND ((processing_status='pending' AND "
    "(next_attempt_at_utc IS NULL OR next_attempt_at_utc<=%s)) OR "
    "(processing_status='retryable_failed' AND next_attempt_at_utc<=%s) OR "
    "(processing_status='processing' AND lease_expires_at_utc<=%s)) "
    "ORDER BY received_at_utc,id LIMIT %s FOR UPDATE SKIP LOCKED"
)
_EXHAUSTED_UPDATE_SQL = (
    "UPDATE line_inbox_events SET processing_status='terminal_failed',"
    "error_code='attempts_exhausted',error_message='LINE webhook attempts exhausted',"
    "processed_at_utc=%s,lease_owner=NULL,lease_acquired_at_utc=NULL,"
    "lease_expires_at_utc=NULL,aggregate_version=aggregate_version+1 "
    "WHERE attempt_count>=max_attempts AND (processing_status='retryable_failed' OR "
    "(processing_status='processing' AND lease_expires_at_utc<=%s))"
)
_CLAIM_UPDATE_SQL = (
    "UPDATE line_inbox_events SET processing_status='processing',attempt_count=attempt_count+1,"
    "lease_owner=%s,lease_acquired_at_utc=%s,lease_expires_at_utc=%s,"
    "aggregate_version=aggregate_version+1,error_code=NULL,error_message=NULL "
    "WHERE event_identity=%s"
)
_COMPLETE_SQL = (
    "UPDATE line_inbox_events SET processing_status=%s,next_attempt_at_utc=%s,"
    "error_code=%s,error_message=%s,processed_at_utc=%s,lease_owner=NULL,"
    "lease_acquired_at_utc=NULL,lease_expires_at_utc=NULL,"
    "aggregate_version=aggregate_version+1 WHERE event_identity=%s "
    "AND lease_owner=%s AND aggregate_version=%s"
)
_NEXT_DUE_SQL = (
    "SELECT MIN(CASE "
    "WHEN processing_status='pending' THEN COALESCE(next_attempt_at_utc,received_at_utc) "
    "WHEN processing_status='retryable_failed' THEN next_attempt_at_utc "
    "WHEN processing_status='processing' THEN lease_expires_at_utc END) AS next_due_at_utc "
    "FROM line_inbox_events WHERE processing_status IN "
    "('pending','retryable_failed','processing')"
)
_TRANSITION_SQL = (
    "UPDATE line_inbox_events SET processing_status=%s,"
    "aggregate_version=aggregate_version+1,"
    "processed_at_utc=CASE WHEN %s IN ('processed','terminal_failed') "
    "THEN CURRENT_TIMESTAMP(6) ELSE processed_at_utc END "
    "WHERE event_identity=%s AND aggregate_version=%s"
)


__all__ = ["MySqlLineWebhookInboxRepository"]

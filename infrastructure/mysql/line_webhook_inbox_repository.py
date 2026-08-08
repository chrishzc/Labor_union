"""MySQL adapter for canonical LINE webhook inbox registration and transitions."""

from __future__ import annotations

from typing import Any

from pymysql.err import IntegrityError

from domains.line.identities import (
    LineDestinationId,
    LineWebhookEventId,
)
from domains.line.webhook import (
    CanonicalLineWebhookEvent,
    LineWebhookInboxSnapshot,
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
    LineWebhookRegistrationOutcome,
)


class MySqlLineWebhookInboxRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

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
    )


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
    "identity_source,is_redelivery,processing_status,aggregate_version "
    "FROM line_inbox_events WHERE event_identity=%s"
)
_TRANSITION_SQL = (
    "UPDATE line_inbox_events SET processing_status=%s,"
    "aggregate_version=aggregate_version+1,"
    "processed_at_utc=CASE WHEN %s IN ('processed','terminal_failed') "
    "THEN CURRENT_TIMESTAMP(6) ELSE processed_at_utc END "
    "WHERE event_identity=%s AND aggregate_version=%s"
)


__all__ = ["MySqlLineWebhookInboxRepository"]

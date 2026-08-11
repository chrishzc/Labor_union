"""MySQL adapters for LINE idempotency receipts, outbox intents, and audit events."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pymysql.err import IntegrityError

from infrastructure.mysql.line_repository_support import (
    aware_utc,
    canonical_json_value,
    database_utc,
    mysql_error_code,
    optional_row,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey, IdempotencyReceipt
from shared_kernel.ports import OutboxIntent
from subsystems.line.ports import LineAuditIntent
from subsystems.line.outbox_contracts import (
    ClaimLineOutboxQuery,
    CompleteLineOutboxCommand,
    LineOutboxWorkItem,
)

_DEFAULT_COMMAND_FAMILY = "line_integration"


class MySqlLineIdempotencyReceiptRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, key: IdempotencyKey) -> IdempotencyReceipt | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = optional_row(cursor.fetchone())
        if row is None:
            return None
        return IdempotencyReceipt(
            IdempotencyKey(str(row["idempotency_key"])),
            PreviewFingerprint(str(row["payload_fingerprint"])),
            str(row["result_reference"]),
        )

    def append(self, receipt: IdempotencyReceipt) -> None:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    _RECEIPT_INSERT_SQL,
                    (
                        receipt.key.value,
                        _DEFAULT_COMMAND_FAMILY,
                        receipt.payload_fingerprint.value,
                        receipt.result_reference,
                        receipt.key.value,
                    ),
                )
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            existing = self.get(receipt.key)
            if existing != receipt:
                raise RuntimeError("line_idempotency_receipt_conflict") from error


class MySqlLineOutboxWriter:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def append(self, intent: OutboxIntent) -> int:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    _OUTBOX_INSERT_SQL,
                    (
                        intent.aggregate_type,
                        intent.aggregate_identity,
                        intent.intent_type,
                        intent.payload_json,
                        intent.idempotency_identity,
                    ),
                )
                return int(cursor.lastrowid)
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            return self._existing_id(intent)

    def _existing_id(self, intent: OutboxIntent) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(_OUTBOX_SELECT_SQL, (intent.idempotency_identity,))
            row = optional_row(cursor.fetchone())
        if row is None:
            raise RuntimeError("line_outbox_duplicate_missing")
        actual = (
            str(row["aggregate_type"]),
            str(row["aggregate_identity"]),
            str(row["intent_type"]),
            canonical_json_value(row["payload_snapshot"]),
        )
        expected = (
            intent.aggregate_type,
            intent.aggregate_identity,
            intent.intent_type,
            intent.payload_json,
        )
        if actual != expected:
            raise RuntimeError("line_outbox_idempotency_conflict")
        return int(row["id"])

    def claim(self, query: ClaimLineOutboxQuery) -> tuple[LineOutboxWorkItem, ...]:
        lease_expires_at = query.now + timedelta(seconds=90)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _OUTBOX_CLAIM_SQL,
                (
                    query.intent_type,
                    database_utc(query.now),
                    database_utc(query.now),
                    query.batch_size,
                ),
            )
            rows = tuple(cursor.fetchall() or ())
            identifiers = tuple(int(row["id"]) for row in rows)
            for outbox_id in identifiers:
                cursor.execute(
                    _OUTBOX_CLAIM_UPDATE_SQL,
                    (
                        query.lease_owner,
                        database_utc(lease_expires_at),
                        outbox_id,
                    ),
                )
            result = []
            for outbox_id in identifiers:
                cursor.execute(_OUTBOX_WORK_SELECT_SQL, (outbox_id,))
                row = optional_row(cursor.fetchone())
                if row is not None:
                    result.append(_outbox_work_item(row))
        return tuple(result)

    def complete(self, command: CompleteLineOutboxCommand) -> None:
        item = command.work_item
        attempts = item.attempt_count + 1
        if command.succeeded:
            status = "completed"
            next_attempt_at = None
        elif not command.retryable or attempts >= item.maximum_attempts:
            status = "dead"
            next_attempt_at = None
        else:
            status = "pending"
            next_attempt_at = command.completed_at + timedelta(
                seconds=command.retry_after_seconds
            )
        with self._connection.cursor() as cursor:
            cursor.execute(
                _OUTBOX_COMPLETE_SQL,
                (
                    status,
                    attempts,
                    database_utc(next_attempt_at) if next_attempt_at else None,
                    command.error_code,
                    command.error_message,
                    database_utc(command.completed_at) if command.succeeded else None,
                    item.outbox_id,
                    item.lease_owner,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_outbox_lease_lost")

    def next_due_at(self, intent_type: str = "line.media.archive"):
        with self._connection.cursor() as cursor:
            cursor.execute(_OUTBOX_NEXT_DUE_SQL, (intent_type,))
            row = optional_row(cursor.fetchone())
        value = None if row is None else row.get("next_due_at_utc")
        return None if value is None else aware_utc(value)


class MySqlLineAuditRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def append(self, intent: LineAuditIntent) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _AUDIT_INSERT_SQL,
                (
                    intent.action,
                    intent.actor_id,
                    intent.aggregate_type,
                    intent.aggregate_identity,
                ),
            )


_RECEIPT_SELECT_SQL = (
    "SELECT idempotency_key,payload_fingerprint,result_reference "
    "FROM line_command_receipts WHERE idempotency_key=%s"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO line_command_receipts (idempotency_key,command_family,"
    "payload_fingerprint,result_reference,correlation_id) VALUES (%s,%s,%s,%s,%s)"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO line_domain_outbox (aggregate_type,aggregate_identity,intent_type,"
    "payload_snapshot,idempotency_identity) VALUES (%s,%s,%s,%s,%s)"
)
_OUTBOX_SELECT_SQL = (
    "SELECT id,aggregate_type,aggregate_identity,intent_type,"
    "CAST(payload_snapshot AS CHAR) AS payload_snapshot "
    "FROM line_domain_outbox WHERE idempotency_identity=%s"
)
_OUTBOX_WORK_COLUMNS = (
    "id,aggregate_type,aggregate_identity,intent_type,"
    "CAST(payload_snapshot AS CHAR) AS payload_snapshot,attempt_count,max_attempts,"
    "lease_owner,lease_expires_at_utc"
)
_OUTBOX_WORK_SELECT_SQL = (
    f"SELECT {_OUTBOX_WORK_COLUMNS} FROM line_domain_outbox WHERE id=%s"
)
_OUTBOX_CLAIM_SQL = (
    f"SELECT {_OUTBOX_WORK_COLUMNS} FROM line_domain_outbox WHERE "
    "intent_type=%s AND ((processing_status='pending' "
    "AND (next_attempt_at_utc IS NULL OR next_attempt_at_utc<=%s)) "
    "OR (processing_status='processing' AND lease_expires_at_utc<=%s) "
    ") ORDER BY COALESCE(next_attempt_at_utc,created_at_utc),id LIMIT %s "
    "FOR UPDATE SKIP LOCKED"
)
_OUTBOX_CLAIM_UPDATE_SQL = (
    "UPDATE line_domain_outbox SET processing_status='processing',lease_owner=%s,"
    "lease_expires_at_utc=%s WHERE id=%s"
)
_OUTBOX_COMPLETE_SQL = (
    "UPDATE line_domain_outbox SET processing_status=%s,attempt_count=%s,"
    "next_attempt_at_utc=%s,error_code=%s,error_message=%s,completed_at_utc=%s,"
    "lease_owner=NULL,lease_expires_at_utc=NULL WHERE id=%s AND lease_owner=%s "
    "AND processing_status='processing'"
)
_OUTBOX_NEXT_DUE_SQL = (
    "SELECT MIN(CASE WHEN processing_status='pending' THEN "
    "COALESCE(next_attempt_at_utc,created_at_utc) "
    "WHEN processing_status='processing' THEN lease_expires_at_utc END) AS next_due_at_utc "
    "FROM line_domain_outbox WHERE intent_type=%s "
    "AND processing_status IN ('pending','processing')"
)
_AUDIT_INSERT_SQL = (
    "INSERT INTO line_domain_audit_events (action,actor_id,aggregate_type,"
    "aggregate_identity) VALUES (%s,%s,%s,%s)"
)


def _outbox_work_item(row):
    return LineOutboxWorkItem(
        int(row["id"]),
        str(row["aggregate_type"]),
        str(row["aggregate_identity"]),
        str(row["intent_type"]),
        canonical_json_value(row["payload_snapshot"]),
        int(row["attempt_count"]),
        int(row["max_attempts"]),
        str(row["lease_owner"]),
        aware_utc(row["lease_expires_at_utc"]),
    )


__all__ = [
    "MySqlLineAuditRepository",
    "MySqlLineIdempotencyReceiptRepository",
    "MySqlLineOutboxWriter",
]

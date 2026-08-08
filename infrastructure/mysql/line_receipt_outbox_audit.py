"""MySQL adapters for LINE idempotency receipts, outbox intents, and audit events."""

from __future__ import annotations

from typing import Any

from pymysql.err import IntegrityError

from infrastructure.mysql.line_repository_support import (
    canonical_json_value,
    mysql_error_code,
    optional_row,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey, IdempotencyReceipt
from shared_kernel.ports import OutboxIntent
from subsystems.line.ports import LineAuditIntent

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
_AUDIT_INSERT_SQL = (
    "INSERT INTO line_domain_audit_events (action,actor_id,aggregate_type,"
    "aggregate_identity) VALUES (%s,%s,%s,%s)"
)


__all__ = [
    "MySqlLineAuditRepository",
    "MySqlLineIdempotencyReceiptRepository",
    "MySqlLineOutboxWriter",
]

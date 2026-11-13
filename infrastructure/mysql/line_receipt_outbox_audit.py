"""MySQL adapters for LINE idempotency receipts, outbox intents, and audit events."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from hashlib import sha256
from typing import Any

from pymysql.err import IntegrityError

from domains.line.identities import LineUserId
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
    IDENTITY_MENU_RESET_INTENT,
    RICH_MENU_BINDING_INTENT,
    RICH_MENU_BINDING_MAX_ATTEMPTS,
    RICH_MENU_BINDING_WINDOW,
    ClaimLineOutboxQuery,
    CompleteLineOutboxCommand,
    LineOutboxWorkItem,
)

_DEFAULT_COMMAND_FAMILY = "line_integration"


class MySqlLineIdempotencyReceiptRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, key: IdempotencyKey, *, for_update: bool = False) -> IdempotencyReceipt | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL + (" FOR UPDATE" if for_update else ""), (key.value,))
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
        menu_binding = intent.intent_type == RICH_MENU_BINDING_INTENT
        if menu_binding:
            self.lock_menu_user(LineUserId(intent.aggregate_identity))
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    _OUTBOX_MENU_INSERT_SQL if menu_binding else _OUTBOX_INSERT_SQL,
                    (
                        intent.aggregate_type,
                        intent.aggregate_identity,
                        intent.intent_type,
                        intent.payload_json,
                        intent.idempotency_identity,
                    ) + ((RICH_MENU_BINDING_MAX_ATTEMPTS,) if menu_binding else ()),
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
        reserve_attempt = query.intent_type == RICH_MENU_BINDING_INTENT
        lease_expires_at = query.now + timedelta(seconds=90)
        now = database_utc(query.now)
        with self._connection.cursor() as cursor:
            if reserve_attempt:
                # Older rows used the DB session's local wall clock. Clamp only
                # future-dated legacy rows once, without resetting their attempts.
                cursor.execute(_OUTBOX_MENU_LEGACY_CLOCK_SELECT_SQL, (query.intent_type, now, now))
                for row in cursor.fetchall() or ():
                    cursor.execute(_OUTBOX_MENU_LEGACY_CLOCK_UPDATE_SQL, (now, int(row["id"])))
                expired_before = database_utc(query.now - RICH_MENU_BINDING_WINDOW)
                cursor.execute(_OUTBOX_MENU_SWEEP_SELECT_SQL, (query.intent_type, now, expired_before))
                for row in cursor.fetchall() or ():
                    code = (
                        "rich_menu_binding_deadline_exhausted" if row["created_at_utc"] <= expired_before
                        else "rich_menu_binding_attempts_exhausted"
                    )
                    cursor.execute(_OUTBOX_MENU_EXHAUSTED_SQL, (code, code, int(row["id"])))
            claim_sql = _OUTBOX_MENU_CLAIM_SQL if reserve_attempt else _OUTBOX_CLAIM_SQL
            claim_params = (query.intent_type, now, now)
            if reserve_attempt:
                claim_params += (expired_before,)
            cursor.execute(
                claim_sql, (*claim_params, query.batch_size),
            )
            rows = tuple(cursor.fetchall() or ())
            result = []
            for row in rows:
                outbox_id = int(row["id"])
                if reserve_attempt:
                    deadline = aware_utc(row["created_at_utc"]) + RICH_MENU_BINDING_WINDOW
                    attempts = int(row["attempt_count"])
                    cursor.execute(
                        _OUTBOX_MENU_CLAIM_UPDATE_SQL,
                        (query.lease_owner, database_utc(lease_expires_at), outbox_id),
                    )
                    row = dict(row, lease_owner=query.lease_owner,
                               lease_expires_at_utc=lease_expires_at,
                               attempt_count=attempts + 1)
                    result.append(_outbox_work_item(row, deadline))
                    continue
                cursor.execute(
                    _OUTBOX_CLAIM_UPDATE_SQL,
                    (
                        query.lease_owner,
                        database_utc(lease_expires_at),
                        outbox_id,
                    ),
                )
                cursor.execute(_OUTBOX_WORK_SELECT_SQL, (outbox_id,))
                row = optional_row(cursor.fetchone())
                if row is not None:
                    result.append(_outbox_work_item(row))
        return tuple(result)

    def complete(self, command: CompleteLineOutboxCommand) -> None:
        item = command.work_item
        attempts = item.attempt_count if item.attempt_reserved else item.attempt_count + 1
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
                    database_utc(item.lease_expires_at),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("line_outbox_lease_lost")

    def lock_menu_user(self, line_user_id: LineUserId) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT line_user_id FROM line_platform_users WHERE line_user_id=%s FOR UPDATE",
                (line_user_id.value,),
            )
            if cursor.fetchone() is None:
                raise LookupError("line_platform_user_not_found")

    @contextmanager
    def menu_provider_lock(self, line_user_id: LineUserId):
        digest = sha256(line_user_id.value.encode("utf-8")).hexdigest()
        name = f"line-menu:{digest[:54]}"
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s,0) AS acquired", (name,))
            acquired = bool((cursor.fetchone() or {}).get("acquired"))
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    with self._connection.cursor() as cursor:
                        cursor.execute("SELECT RELEASE_LOCK(%s)", (name,))
                finally:
                    self._connection.rollback()

    def lock_menu_lease(self, item: LineOutboxWorkItem, now: datetime) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM line_domain_outbox WHERE id=%s AND lease_owner=%s "
                "AND lease_expires_at_utc=%s AND lease_expires_at_utc>%s "
                "AND processing_status='processing' FOR UPDATE",
                (item.outbox_id, item.lease_owner, database_utc(item.lease_expires_at), database_utc(now)),
            )
            return cursor.fetchone() is not None

    def latest_menu_intent_id(self, line_user_id: LineUserId) -> int | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(id) AS id FROM ("
                "SELECT id FROM line_domain_outbox WHERE aggregate_type='line_identity' "
                "AND aggregate_identity=%s AND intent_type=%s "
                "UNION ALL SELECT reset.id FROM line_identity_revocation_requests request "
                "JOIN line_domain_outbox reset ON reset.aggregate_identity="
                "CAST(request.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
                "AND reset.aggregate_type='line_identity_revocation' AND reset.intent_type=%s "
                "WHERE request.line_user_id=%s) intents",
                (line_user_id.value, RICH_MENU_BINDING_INTENT, IDENTITY_MENU_RESET_INTENT, line_user_id.value),
            )
            row = optional_row(cursor.fetchone())
        return int(row["id"]) if row and row["id"] is not None else None

    def menu_reset_pending(self, line_user_id: LineUserId) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM line_identity_revocation_requests WHERE line_user_id=%s "
                "AND request_status='pending_menu_reset' LIMIT 1",
                (line_user_id.value,),
            )
            return cursor.fetchone() is not None

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
_OUTBOX_MENU_INSERT_SQL = (
    "INSERT INTO line_domain_outbox (aggregate_type,aggregate_identity,intent_type,"
    "payload_snapshot,idempotency_identity,max_attempts,created_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))"
)
_OUTBOX_SELECT_SQL = (
    "SELECT id,aggregate_type,aggregate_identity,intent_type,"
    "CAST(payload_snapshot AS CHAR) AS payload_snapshot "
    "FROM line_domain_outbox WHERE idempotency_identity=%s"
)
_OUTBOX_WORK_COLUMNS = (
    "id,aggregate_type,aggregate_identity,intent_type,"
    "CAST(payload_snapshot AS CHAR) AS payload_snapshot,attempt_count,max_attempts,"
    "lease_owner,lease_expires_at_utc,created_at_utc,idempotency_identity"
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
_OUTBOX_MENU_CLAIM_SQL = _OUTBOX_CLAIM_SQL.replace(
    ") ORDER BY",
    ") AND created_at_utc>%s AND attempt_count<max_attempts ORDER BY",
)
_OUTBOX_CLAIM_UPDATE_SQL = (
    "UPDATE line_domain_outbox SET processing_status='processing',lease_owner=%s,"
    "lease_expires_at_utc=%s WHERE id=%s"
)
_OUTBOX_MENU_CLAIM_UPDATE_SQL = (
    "UPDATE line_domain_outbox SET processing_status='processing',lease_owner=%s,"
    "lease_expires_at_utc=%s,attempt_count=attempt_count+1 WHERE id=%s"
)
_OUTBOX_MENU_SWEEP_SELECT_SQL = (
    "SELECT id,created_at_utc FROM line_domain_outbox WHERE intent_type=%s "
    "AND (processing_status='pending' OR "
    "(processing_status='processing' AND lease_expires_at_utc<=%s)) "
    "AND (created_at_utc<=%s OR attempt_count>=max_attempts) FOR UPDATE SKIP LOCKED"
)
_OUTBOX_MENU_LEGACY_CLOCK_SELECT_SQL = (
    "SELECT id FROM line_domain_outbox "
    "WHERE intent_type=%s AND max_attempts=3 AND created_at_utc>%s "
    "AND (processing_status='pending' OR "
    "(processing_status='processing' AND lease_expires_at_utc<=%s)) FOR UPDATE SKIP LOCKED"
)
_OUTBOX_MENU_LEGACY_CLOCK_UPDATE_SQL = (
    "UPDATE line_domain_outbox SET created_at_utc=%s WHERE id=%s"
)
_OUTBOX_MENU_EXHAUSTED_SQL = (
    "UPDATE line_domain_outbox SET processing_status='dead',"
    "error_message=COALESCE(error_message,%s),error_code=%s,"
    "next_attempt_at_utc=NULL,lease_owner=NULL,lease_expires_at_utc=NULL WHERE id=%s"
)
_OUTBOX_COMPLETE_SQL = (
    "UPDATE line_domain_outbox SET processing_status=%s,attempt_count=%s,"
    "next_attempt_at_utc=%s,error_code=%s,error_message=%s,completed_at_utc=%s,"
    "lease_owner=NULL,lease_expires_at_utc=NULL WHERE id=%s AND lease_owner=%s "
    "AND lease_expires_at_utc=%s AND processing_status='processing'"
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


def _outbox_work_item(row, deadline=None):
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
        deadline,
        deadline is not None,
        str(row["idempotency_identity"]),
    )


__all__ = [
    "MySqlLineAuditRepository",
    "MySqlLineIdempotencyReceiptRepository",
    "MySqlLineOutboxWriter",
]

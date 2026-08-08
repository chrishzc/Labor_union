"""MySQL adapter for canonical LINE delivery task enqueue, lease, and attempts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pymysql.err import IntegrityError

from domains.line.delivery import (
    LineDeliveryAttemptOutcome,
    LineDeliveryLease,
    LineDeliveryRequest,
    LineDeliveryStatus,
    LineDeliveryTaskSnapshot,
    LineMessageKind,
    LineRetryPolicy,
    plan_delivery_attempt,
    transition_delivery_status,
)
from domains.line.identities import LineDeliveryTaskId
from infrastructure.mysql.line_repository_support import (
    aware_utc,
    canonical_json_value,
    database_utc,
    mysql_error_code,
    optional_row,
    recipient,
)
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import (
    CancelLineDeliveryTaskCommand,
    ClaimLineDeliveryTasksQuery,
    EnqueueLineDeliveryResult,
    LineDeliveryCommandOutcome,
    RecordLineDeliveryAttemptCommand,
    RecordLineDeliveryAttemptResult,
    provider_attempt_outcome,
)


class MySqlLineDeliveryTaskRepository:
    def __init__(
        self,
        connection: Any,
        *,
        lease_duration_seconds: int = 60,
        retry_base_delay_seconds: int = 5,
        retry_maximum_delay_seconds: int = 300,
    ) -> None:
        self._connection = connection
        self._lease_duration = timedelta(seconds=lease_duration_seconds)
        self._retry_base_delay = retry_base_delay_seconds
        self._retry_maximum_delay = retry_maximum_delay_seconds

    def enqueue(self, request: LineDeliveryRequest) -> EnqueueLineDeliveryResult:
        try:
            task_id = self._insert(request)
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            return self._existing_enqueue(request)
        return EnqueueLineDeliveryResult(
            LineDeliveryCommandOutcome.CREATED,
            LineDeliveryTaskId(task_id),
            LineDeliveryStatus.PENDING,
        )

    def get(self, task_id: LineDeliveryTaskId) -> LineDeliveryTaskSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_SELECT_SQL, (task_id.value,))
            row = optional_row(cursor.fetchone())
        return None if row is None else _snapshot(row)

    def claim(
        self,
        query: ClaimLineDeliveryTasksQuery,
    ) -> tuple[LineDeliveryTaskSnapshot, ...]:
        lease_expires_at = query.now + self._lease_duration
        with self._connection.cursor() as cursor:
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
            task_ids = tuple(int(row["id"]) for row in rows)
            for task_id in task_ids:
                cursor.execute(
                    _CLAIM_UPDATE_SQL,
                    (
                        query.lease_owner,
                        database_utc(query.now),
                        database_utc(lease_expires_at),
                        task_id,
                    ),
                )
            claimed = tuple(self._load_rows(cursor, task_ids))
        return tuple(_snapshot(row) for row in claimed)

    def record_attempt(
        self,
        command: RecordLineDeliveryAttemptCommand,
    ) -> RecordLineDeliveryAttemptResult:
        with self._connection.cursor() as cursor:
            existing = self._existing_attempt(cursor, command)
            if existing is not None:
                return self._existing_attempt_result(cursor, command, existing)
            row = self._locked_task(cursor, command.task.task_id)
            self._require_matching_lease(row, command)
            completed_attempts = int(row["completed_attempts"]) + 1
            policy = LineRetryPolicy(
                int(row["max_attempts"]),
                self._retry_base_delay,
                self._retry_maximum_delay,
            )
            plan = plan_delivery_attempt(
                policy,
                completed_attempts=completed_attempts,
                outcome=provider_attempt_outcome(command.provider_outcome),
                completed_at=command.completed_at,
                retry_after_seconds=command.provider_outcome.retry_after_seconds,
            )
            self._insert_attempt(cursor, command, completed_attempts)
            self._finish_attempt(cursor, command, completed_attempts, plan)
        return RecordLineDeliveryAttemptResult(command.task.task_id, plan)

    def _existing_attempt(self, cursor, command):
        cursor.execute(_ATTEMPT_SELECT_BY_KEY_SQL, (command.idempotency_key.value,))
        return optional_row(cursor.fetchone())

    def _existing_attempt_result(self, cursor, command, attempt):
        self._validate_existing_attempt(command, attempt)
        cursor.execute(_SELECT_SQL, (command.task.task_id.value,))
        task_row = optional_row(cursor.fetchone())
        if task_row is None:
            raise RuntimeError("line_delivery_attempt_task_missing")
        policy = LineRetryPolicy(
            int(task_row["max_attempts"]),
            self._retry_base_delay,
            self._retry_maximum_delay,
        )
        plan = plan_delivery_attempt(
            policy,
            completed_attempts=int(attempt["attempt_number"]),
            outcome=LineDeliveryAttemptOutcome(str(attempt["outcome"])),
            completed_at=aware_utc(attempt["completed_at_utc"]),
            retry_after_seconds=attempt.get("retry_after_seconds"),
        )
        return RecordLineDeliveryAttemptResult(command.task.task_id, plan)

    def _validate_existing_attempt(self, command, attempt):
        outcome = command.provider_outcome
        actual = (
            int(attempt["task_id"]),
            str(attempt["provider_outcome_type"]),
            _optional_text(attempt.get("provider_message_id")),
            _optional_text(attempt.get("error_code")),
            attempt.get("retry_after_seconds"),
            str(attempt["correlation_id"]),
        )
        expected = (
            command.task.task_id.value,
            outcome.outcome_type.value,
            outcome.provider_message_id.value if outcome.provider_message_id else None,
            outcome.error_code,
            outcome.retry_after_seconds,
            command.correlation_id.value,
        )
        if actual != expected:
            raise RuntimeError("line_delivery_attempt_idempotency_conflict")

    def cancel(
        self,
        command: CancelLineDeliveryTaskCommand,
    ) -> LineDeliveryTaskSnapshot:
        with self._connection.cursor() as cursor:
            row = self._locked_task(cursor, command.task_id)
            current = LineDeliveryStatus(str(row["processing_status"]))
            if current is LineDeliveryStatus.CANCELLED:
                return _snapshot(row)
            transition_delivery_status(current, LineDeliveryStatus.CANCELLED)
            cursor.execute(_CANCEL_SQL, (command.task_id.value, current.value))
            if cursor.rowcount != 1:
                raise RuntimeError("line_delivery_cancel_conflict")
            cursor.execute(_SELECT_SQL, (command.task_id.value,))
            updated = cursor.fetchone()
        return _snapshot(updated)

    def next_due_at(self):
        with self._connection.cursor() as cursor:
            cursor.execute(_NEXT_DUE_SQL)
            row = optional_row(cursor.fetchone())
        due_at = None if row is None else row.get("next_due_at_utc")
        return aware_utc(due_at) if due_at is not None else None

    def cancel_pending_for_recipient(self, line_user_id) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(_CANCEL_RECIPIENT_SQL, (line_user_id.value,))
            return int(cursor.rowcount)

    def _insert(self, request: LineDeliveryRequest) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _INSERT_SQL,
                (
                    request.recipient.recipient_type.value,
                    request.recipient.identity.value,
                    request.message_kind.value,
                    request.payload_json,
                    request.fingerprint.value,
                    database_utc(request.scheduled_at),
                    request.source_aggregate_type,
                    request.source_aggregate_identity,
                    request.idempotency_key.value,
                    request.correlation_id.value,
                ),
            )
            return int(cursor.lastrowid)

    def _existing_enqueue(
        self,
        request: LineDeliveryRequest,
    ) -> EnqueueLineDeliveryResult:
        with self._connection.cursor() as cursor:
            cursor.execute(_SELECT_BY_KEY_SQL, (request.idempotency_key.value,))
            row = optional_row(cursor.fetchone())
        if row is None:
            raise RuntimeError("line_delivery_duplicate_missing")
        if str(row["payload_fingerprint"]) != request.fingerprint.value:
            raise RuntimeError("line_delivery_idempotency_conflict")
        return EnqueueLineDeliveryResult(
            LineDeliveryCommandOutcome.EXISTING,
            LineDeliveryTaskId(int(row["id"])),
            LineDeliveryStatus(str(row["processing_status"])),
        )

    def _locked_task(self, cursor: Any, task_id: LineDeliveryTaskId):
        cursor.execute(_SELECT_SQL + " FOR UPDATE", (task_id.value,))
        row = optional_row(cursor.fetchone())
        if row is None:
            raise LookupError("line_delivery_task_not_found")
        return row

    def _require_matching_lease(
        self,
        row: dict[str, object],
        command: RecordLineDeliveryAttemptCommand,
    ) -> None:
        actual = (
            str(row["processing_status"]),
            _optional_text(row.get("lease_owner")),
            aware_utc(row["lease_acquired_at_utc"]),
            aware_utc(row["lease_expires_at_utc"]),
        )
        expected = (
            LineDeliveryStatus.PROCESSING.value,
            command.lease.owner,
            command.lease.acquired_at,
            command.lease.expires_at,
        )
        if actual != expected or command.completed_at > command.lease.expires_at:
            raise RuntimeError("line_delivery_lease_lost")

    def _insert_attempt(self, cursor, command, attempt_number):
        outcome = command.provider_outcome
        cursor.execute(
            _ATTEMPT_INSERT_SQL,
            (
                command.task.task_id.value,
                attempt_number,
                provider_attempt_outcome(outcome).value,
                outcome.outcome_type.value,
                outcome.provider_message_id.value if outcome.provider_message_id else None,
                outcome.error_code,
                outcome.error_message,
                outcome.retry_after_seconds,
                database_utc(command.lease.acquired_at),
                database_utc(command.completed_at),
                command.idempotency_key.value,
                command.correlation_id.value,
            ),
        )

    def _finish_attempt(self, cursor, command, attempts, plan):
        outcome = command.provider_outcome
        cursor.execute(
            _ATTEMPT_UPDATE_TASK_SQL,
            (
                plan.resulting_status.value,
                attempts,
                database_utc(plan.next_attempt_at) if plan.next_attempt_at else None,
                outcome.provider_message_id.value if outcome.provider_message_id else None,
                outcome.error_code,
                outcome.error_message,
                database_utc(command.completed_at)
                if plan.resulting_status is LineDeliveryStatus.SENT else None,
                database_utc(command.completed_at)
                if plan.resulting_status is LineDeliveryStatus.FAILED else None,
                command.task.task_id.value,
                command.lease.owner,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("line_delivery_lease_lost")

    def _load_rows(self, cursor, task_ids):
        for task_id in task_ids:
            cursor.execute(_SELECT_SQL, (task_id,))
            row = optional_row(cursor.fetchone())
            if row is not None:
                yield row


def _snapshot(row: object) -> LineDeliveryTaskSnapshot:
    if not isinstance(row, dict):
        row = dict(row)
    task_id = LineDeliveryTaskId(int(row["id"]))
    request = LineDeliveryRequest(
        recipient(str(row["recipient_type"]), str(row["recipient_identity"])),
        LineMessageKind(str(row["message_kind"])),
        canonical_json_value(row["payload_snapshot"]),
        aware_utc(row["scheduled_at_utc"]),
        IdempotencyKey(str(row["idempotency_key"])),
        CorrelationId(str(row["correlation_id"])),
        str(row["source_aggregate_type"]),
        str(row["source_aggregate_identity"]),
    )
    lease = _lease(row, task_id)
    return LineDeliveryTaskSnapshot(
        task_id,
        request,
        LineDeliveryStatus(str(row["processing_status"])),
        int(row["completed_attempts"]),
        lease,
    )


def _lease(row: dict[str, object], task_id: LineDeliveryTaskId):
    owner = _optional_text(row.get("lease_owner"))
    if owner is None:
        return None
    return LineDeliveryLease(
        task_id,
        owner,
        aware_utc(row["lease_acquired_at_utc"]),
        aware_utc(row["lease_expires_at_utc"]),
    )


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


_SELECT_COLUMNS = (
    "id,recipient_type,recipient_identity,message_kind,payload_snapshot,"
    "payload_fingerprint,scheduled_at_utc,source_aggregate_type,"
    "source_aggregate_identity,idempotency_key,correlation_id,processing_status,"
    "completed_attempts,max_attempts,next_attempt_at_utc,lease_owner,"
    "lease_acquired_at_utc,lease_expires_at_utc"
)
_INSERT_SQL = (
    "INSERT INTO line_delivery_tasks (recipient_type,recipient_identity,"
    "message_kind,payload_snapshot,payload_fingerprint,scheduled_at_utc,"
    "source_aggregate_type,source_aggregate_identity,idempotency_key,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_SELECT_SQL = f"SELECT {_SELECT_COLUMNS} FROM line_delivery_tasks WHERE id=%s"
_SELECT_BY_KEY_SQL = (
    f"SELECT {_SELECT_COLUMNS} FROM line_delivery_tasks WHERE idempotency_key=%s"
)
_CLAIM_CANDIDATES_SQL = (
    f"SELECT {_SELECT_COLUMNS} FROM line_delivery_tasks WHERE "
    "source_aggregate_type<>'legacy_line_task' AND "
    "((processing_status='pending' AND scheduled_at_utc<=%s) OR "
    "(processing_status='retryable_failed' AND next_attempt_at_utc<=%s) OR "
    "(processing_status='processing' AND lease_expires_at_utc<=%s)) "
    "ORDER BY COALESCE(next_attempt_at_utc,scheduled_at_utc),id LIMIT %s "
    "FOR UPDATE SKIP LOCKED"
)
_NEXT_DUE_SQL = (
    "SELECT MIN(CASE "
    "WHEN processing_status='pending' THEN scheduled_at_utc "
    "WHEN processing_status='retryable_failed' THEN next_attempt_at_utc "
    "WHEN processing_status='processing' THEN lease_expires_at_utc END) AS next_due_at_utc "
    "FROM line_delivery_tasks WHERE source_aggregate_type<>'legacy_line_task' "
    "AND processing_status IN ('pending','retryable_failed','processing')"
)
_CLAIM_UPDATE_SQL = (
    "UPDATE line_delivery_tasks SET processing_status='processing',lease_owner=%s,"
    "lease_acquired_at_utc=%s,lease_expires_at_utc=%s WHERE id=%s"
)
_ATTEMPT_INSERT_SQL = (
    "INSERT INTO line_delivery_attempt_events (task_id,attempt_number,outcome,"
    "provider_outcome_type,provider_message_id,error_code,error_message,"
    "retry_after_seconds,started_at_utc,completed_at_utc,idempotency_key,"
    "correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_ATTEMPT_SELECT_BY_KEY_SQL = (
    "SELECT task_id,attempt_number,outcome,provider_outcome_type,"
    "provider_message_id,error_code,retry_after_seconds,completed_at_utc,"
    "correlation_id FROM line_delivery_attempt_events WHERE idempotency_key=%s"
)
_ATTEMPT_UPDATE_TASK_SQL = (
    "UPDATE line_delivery_tasks SET processing_status=%s,completed_attempts=%s,"
    "next_attempt_at_utc=%s,provider_message_id=%s,error_code=%s,error_message=%s,"
    "sent_at_utc=%s,failed_at_utc=%s,lease_owner=NULL,lease_acquired_at_utc=NULL,"
    "lease_expires_at_utc=NULL WHERE id=%s AND lease_owner=%s "
    "AND processing_status='processing'"
)
_CANCEL_SQL = (
    "UPDATE line_delivery_tasks SET processing_status='cancelled',lease_owner=NULL,"
    "lease_acquired_at_utc=NULL,lease_expires_at_utc=NULL WHERE id=%s "
    "AND processing_status=%s"
)
_CANCEL_RECIPIENT_SQL = (
    "UPDATE line_delivery_tasks SET processing_status='cancelled',lease_owner=NULL,"
    "lease_acquired_at_utc=NULL,lease_expires_at_utc=NULL WHERE recipient_type='user' "
    "AND recipient_identity=%s AND processing_status IN ('pending','retryable_failed')"
)


__all__ = ["MySqlLineDeliveryTaskRepository"]

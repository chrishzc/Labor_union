"""MySQL-backed durable command queue and compatible job-status reader."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pymysql.connections import Connection

from shared_kernel.durable_job_queue import (
    DurableJobCommand,
    DurableJobLease,
    DurableJobStateConflict,
)
from shared_kernel.identities import IdempotencyKey


@dataclass(frozen=True, slots=True)
class BackgroundJob:
    job_id: str
    command_identity: str
    status: str
    receipt_payload: dict[str, Any] | None
    error_payload: dict[str, Any] | None
    command_type: str | None = None
    attempt_count: int = 0
    max_attempts: int = 0
    result_reference: str | None = None


class JobIdempotencyConflict(Exception):
    """A command identity is already represented by one durable job."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__(f"Job already exists with id {job_id}")


class DurableJobSchemaNotReady(RuntimeError):
    """The current database cannot safely run the durable command worker."""

    def __init__(self, missing_columns: frozenset[str]):
        required = ", ".join(sorted(missing_columns))
        super().__init__(
            "durable_job_schema_not_ready: missing background_jobs columns "
            f"[{required}]; apply the approved additive release before starting the worker"
        )
        self.missing_columns = missing_columns


_DURABLE_QUEUE_COLUMNS = frozenset(
    {
        "job_id", "command_identity", "command_type", "command_version",
        "command_payload", "submitted_by", "correlation_id", "status",
        "available_at", "attempt_count", "max_attempts", "lease_token",
        "lease_owner", "lease_expires_at", "receipt_payload", "error_payload",
        "result_reference", "completed_at", "created_at", "updated_at",
    }
)


class BackgroundJobRepository:
    def __init__(self, connection: Connection):
        self._connection = connection

    def enqueue_job(self, job_id: str, command_identity: IdempotencyKey) -> str:
        """Keep legacy route-local workers compatible during staged migration."""
        try:
            self._execute(
                "INSERT INTO background_jobs (job_id, command_identity, status) "
                "VALUES (%s, %s, 'queued')",
                (job_id, command_identity.value),
            )
            self._connection.commit()
            return job_id
        except Exception as error:
            self._connection.rollback()
            if "Duplicate entry" in str(error):
                existing = self.get_job_by_identity(command_identity)
                if existing is not None:
                    raise JobIdempotencyConflict(existing.job_id) from error
            raise

    def assert_durable_queue_schema(self) -> None:
        """Fail before job mutation when the current database lacks the queue release."""
        rows = self._fetchall(
            "SELECT column_name AS queue_column_name FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'background_jobs'"
        )
        available_columns = {str(_value(row, "queue_column_name", 0)) for row in rows}
        missing_columns = _DURABLE_QUEUE_COLUMNS - available_columns
        if missing_columns:
            raise DurableJobSchemaNotReady(frozenset(missing_columns))

    def enqueue_command(self, command: DurableJobCommand) -> str:
        """Persist one replayable command envelope before any worker can run it."""
        try:
            self._execute(
                "INSERT INTO background_jobs "
                "(job_id, command_identity, command_type, command_version, "
                "command_payload, submitted_by, correlation_id, status, max_attempts) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', %s)",
                (
                    command.job_id,
                    command.command_identity,
                    command.command_type,
                    command.command_version,
                    json.dumps(command.payload, sort_keys=True),
                    command.submitted_by,
                    command.correlation_id,
                    command.max_attempts,
                ),
            )
            self._connection.commit()
            return command.job_id
        except Exception as error:
            self._connection.rollback()
            if "Duplicate entry" in str(error):
                existing = self.get_job_by_identity_value(command.command_identity)
                if existing is not None:
                    raise JobIdempotencyConflict(existing.job_id) from error
            raise

    def get_job(self, job_id: str) -> BackgroundJob | None:
        row = self._fetchone(
            "SELECT job_id, command_identity, status, receipt_payload, error_payload, "
            "command_type, attempt_count, max_attempts, result_reference "
            "FROM background_jobs WHERE job_id = %s",
            (job_id,),
        )
        return _to_background_job(row)

    def get_job_by_identity(self, command_identity: IdempotencyKey) -> BackgroundJob | None:
        return self.get_job_by_identity_value(command_identity.value)

    def get_job_by_identity_value(self, command_identity: str) -> BackgroundJob | None:
        row = self._fetchone(
            "SELECT job_id, command_identity, status, receipt_payload, error_payload, "
            "command_type, attempt_count, max_attempts, result_reference "
            "FROM background_jobs WHERE command_identity = %s",
            (command_identity,),
        )
        return _to_background_job(row)

    def claim_next_command(self, worker_id: str, lease_seconds: int) -> DurableJobLease | None:
        """Atomically lease one due durable command; legacy jobs are never claimed."""
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        try:
            row = self._fetchone(
                "SELECT job_id, command_identity, command_type, command_version, "
                "command_payload, submitted_by, correlation_id, attempt_count, max_attempts "
                "FROM background_jobs WHERE status = 'queued' AND command_type IS NOT NULL "
                "AND available_at <= CURRENT_TIMESTAMP(6) ORDER BY created_at "
                "LIMIT 1 FOR UPDATE SKIP LOCKED"
            )
            if row is None:
                self._connection.commit()
                return None
            lease_token = str(uuid.uuid4())
            updated = self._execute(
                "UPDATE background_jobs SET status = 'running', attempt_count = attempt_count + 1, "
                "lease_token = %s, lease_owner = %s, "
                "lease_expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s SECOND) "
                "WHERE job_id = %s AND status = 'queued'",
                (lease_token, worker_id, lease_seconds, _value(row, "job_id", 0)),
            )
            if updated != 1:
                raise DurableJobStateConflict("job was claimed by another worker")
            self._connection.commit()
            command = DurableJobCommand(
                job_id=_value(row, "job_id", 0),
                command_identity=_value(row, "command_identity", 1),
                command_type=_value(row, "command_type", 2),
                command_version=int(_value(row, "command_version", 3)),
                payload=_json_payload(_value(row, "command_payload", 4)),
                submitted_by=_value(row, "submitted_by", 5) or "system",
                correlation_id=_value(row, "correlation_id", 6) or "job:" + _value(row, "job_id", 0),
                max_attempts=int(_value(row, "max_attempts", 8)),
            )
            return DurableJobLease(
                command.job_id,
                lease_token,
                command,
                int(_value(row, "attempt_count", 7)) + 1,
            )
        except Exception:
            self._connection.rollback()
            raise

    def requeue_expired_leases(self, retry_delay_seconds: int) -> int:
        """Return abandoned running commands to the queue without changing identity."""
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must not be negative")
        try:
            requeued = self._execute(
                "UPDATE background_jobs SET status = 'queued', lease_token = NULL, "
                "lease_owner = NULL, lease_expires_at = NULL, "
                "available_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s SECOND) "
                "WHERE status = 'running' AND lease_expires_at < CURRENT_TIMESTAMP(6) "
                "AND attempt_count < max_attempts",
                (retry_delay_seconds,),
            )
            exhausted = self._execute(
                "UPDATE background_jobs SET status = 'failed', lease_token = NULL, "
                "lease_owner = NULL, lease_expires_at = NULL, completed_at = CURRENT_TIMESTAMP(6), "
                "error_payload = %s WHERE status = 'running' "
                "AND lease_expires_at < CURRENT_TIMESTAMP(6) AND attempt_count >= max_attempts",
                (json.dumps({"error": {"category": "UNAVAILABLE", "code": "job_lease_expired", "message": "Worker lease expired."}}),),
            )
            self._connection.commit()
            return requeued + exhausted
        except Exception:
            self._connection.rollback()
            raise

    def complete_claimed_job(self, lease: DurableJobLease, receipt: dict[str, Any], result_reference: str) -> None:
        self._transition_claim(lease, "succeeded", receipt, None, result_reference, 0)

    def fail_claimed_job(self, lease: DurableJobLease, error: dict[str, Any], retry_after_seconds: int | None = None) -> None:
        if retry_after_seconds is not None and lease.attempt_count < lease.command.max_attempts:
            self._transition_claim(lease, "queued", None, error, None, retry_after_seconds)
            return
        self._transition_claim(lease, "failed", None, error, None, 0)

    def cancel_queued_job(self, job_id: str) -> None:
        updated = self._execute(
            "UPDATE background_jobs SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP(6) "
            "WHERE job_id = %s AND status = 'queued'",
            (job_id,),
        )
        self._connection.commit()
        if updated != 1:
            raise DurableJobStateConflict("only an unclaimed queued job can be cancelled")

    def mark_running(self, job_id: str) -> None:
        self._execute("UPDATE background_jobs SET status = 'running' WHERE job_id = %s AND status = 'queued'", (job_id,))
        self._connection.commit()

    def mark_succeeded(self, job_id: str, receipt: dict[str, Any]) -> None:
        self._execute("UPDATE background_jobs SET status = 'succeeded', receipt_payload = %s, completed_at = CURRENT_TIMESTAMP(6) WHERE job_id = %s", (json.dumps(receipt), job_id))
        self._connection.commit()

    def mark_failed(self, job_id: str, error: dict[str, Any]) -> None:
        self._execute("UPDATE background_jobs SET status = 'failed', error_payload = %s, completed_at = CURRENT_TIMESTAMP(6) WHERE job_id = %s", (json.dumps(error), job_id))
        self._connection.commit()

    def _transition_claim(self, lease, status, receipt, error, reference, delay_seconds) -> None:
        receipt_payload = json.dumps(receipt) if receipt is not None else None
        error_payload = json.dumps(error) if error is not None else None
        updated = self._execute(
            "UPDATE background_jobs SET status = %s, receipt_payload = %s, error_payload = %s, "
            "result_reference = %s, lease_token = NULL, lease_owner = NULL, lease_expires_at = NULL, "
            "available_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s SECOND), "
            "completed_at = CASE WHEN %s = 'queued' THEN NULL ELSE CURRENT_TIMESTAMP(6) END "
            "WHERE job_id = %s AND status = 'running' AND lease_token = %s",
            (status, receipt_payload, error_payload, reference, delay_seconds, status, lease.job_id, lease.lease_token),
        )
        self._connection.commit()
        if updated != 1:
            raise DurableJobStateConflict("job lease is no longer held")

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._connection.cursor() as cursor:
            return cursor.execute(sql, params)

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()):
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())


def _to_background_job(row: Any) -> BackgroundJob | None:
    if row is None:
        return None
    return BackgroundJob(
        job_id=_value(row, "job_id", 0), command_identity=_value(row, "command_identity", 1),
        status=_value(row, "status", 2), receipt_payload=_json_or_none(_value(row, "receipt_payload", 3)),
        error_payload=_json_or_none(_value(row, "error_payload", 4)), command_type=_value(row, "command_type", 5),
        attempt_count=int(_value(row, "attempt_count", 6) or 0), max_attempts=int(_value(row, "max_attempts", 7) or 0),
        result_reference=_value(row, "result_reference", 8),
    )


def _value(row: Any, key: str, index: int):
    return row[key] if isinstance(row, dict) else row[index]


def _json_or_none(value: Any) -> dict[str, Any] | None:
    return None if value is None else _json_payload(value)


def _json_payload(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else (value or {})

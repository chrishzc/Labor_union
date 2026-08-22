"""
File: background_job_repository.py
Description: 實作 legacy job 相容層與零 hidden commit 的 MySQL canonical Durable Job repository。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pymysql.connections import Connection
from pymysql.err import IntegrityError

from shared_kernel.durable_job_queue import (
    DurableJobCommand,
    DurableJobLease,
    DurableJobStateConflict,
)
from shared_kernel.identities import IdempotencyKey
from subsystems.jobs.contracts import (
    DurableJobCommandConflict,
    DurableJobContractViolation,
    DurableJobFailureOutcome,
    DurableJobSuccessOutcome,
    equality_for,
    equality_mismatches,
    parse_canonical_payload,
    validate_command_key,
)


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

    def enqueue_canonical_command(self, command: DurableJobCommand) -> str:
        """Insert or replay one validated command without owning commit/rollback."""
        validate_command_key(command.command_identity)
        requested_equality = equality_for(
            command.command_type,
            command.command_version,
            command.payload,
            command.submitted_by,
        )
        if (
            not isinstance(command.correlation_id, str)
            or not command.correlation_id
            or len(command.correlation_id) > 191
        ):
            raise DurableJobContractViolation("invalid durable command correlation identity")
        if not isinstance(command.job_id, str) or not command.job_id or len(command.job_id) > 191:
            raise DurableJobContractViolation("invalid durable job identity")
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
                    requested_equality.canonical_payload,
                    command.submitted_by,
                    command.correlation_id,
                    command.max_attempts,
                ),
            )
            return command.job_id
        except Exception as error:
            if not isinstance(error, IntegrityError) or not error.args or error.args[0] != 1062:
                raise
            try:
                stored = self.read_canonical_command_by_identity(command.command_identity)
            except DurableJobContractViolation as stored_error:
                existing = self.get_job_by_identity_value(command.command_identity)
                existing_job_id = command.job_id if existing is None else existing.job_id
                raise DurableJobCommandConflict(
                    existing_job_id,
                    ("command_identity",),
                ) from stored_error
            if stored is None:
                raise DurableJobCommandConflict(command.job_id, ("command_identity",)) from error
            stored_equality = equality_for(
                stored.command_type,
                stored.command_version,
                stored.payload,
                stored.submitted_by,
            )
            mismatches = list(equality_mismatches(requested_equality, stored_equality))
            if stored.command_identity != command.command_identity:
                mismatches.insert(0, "command_identity")
            if mismatches:
                raise DurableJobCommandConflict(stored.job_id, tuple(mismatches)) from error
            return stored.job_id

    def cancel_queued_canonical_job(self, job_id: str) -> None:
        """Cancel one unclaimed queued job without owning commit or rollback."""
        updated = self._execute(
            "UPDATE background_jobs SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP(6) "
            "WHERE job_id = %s AND status = 'queued'",
            (job_id,),
        )
        if updated != 1:
            raise DurableJobStateConflict("job is not queued or no longer exists")

    def read_canonical_command_by_identity(
        self,
        command_identity: str,
    ) -> DurableJobCommand | None:
        """Read the exact persisted equality; invalid or legacy rows fail closed."""
        validate_command_key(command_identity)
        row = self._fetchone(
            "SELECT job_id, command_identity, command_type, command_version, "
            "command_payload, submitted_by, correlation_id, attempt_count, max_attempts "
            "FROM background_jobs WHERE command_identity = %s",
            (command_identity,),
        )
        return None if row is None else _canonical_command_from_row(row)

    def recover_expired_canonical_leases(self, retry_delay_seconds: int) -> int:
        """Recover expired canonical leases without owning commit/rollback."""
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must not be negative")
        requeued = self._execute(
            "UPDATE background_jobs SET status = 'queued', lease_token = NULL, "
            "lease_owner = NULL, lease_expires_at = NULL, "
            "available_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s SECOND) "
            "WHERE status = 'running' AND command_type IS NOT NULL "
            "AND lease_expires_at < CURRENT_TIMESTAMP(6) AND attempt_count < max_attempts",
            (retry_delay_seconds,),
        )
        exhausted_outcome = DurableJobFailureOutcome(
            "unavailable",
            "job_lease_expired",
            "Worker lease expired.",
            retryable=False,
        )
        exhausted = self._execute(
            "UPDATE background_jobs SET status = 'failed', lease_token = NULL, "
            "lease_owner = NULL, lease_expires_at = NULL, completed_at = CURRENT_TIMESTAMP(6), "
            "error_payload = %s WHERE status = 'running' AND command_type IS NOT NULL "
            "AND lease_expires_at < CURRENT_TIMESTAMP(6) AND attempt_count >= max_attempts",
            (_closed_payload_json(exhausted_outcome.to_payload()),),
        )
        return requeued + exhausted

    def claim_next_canonical_command(
        self,
        worker_id: str,
        lease_seconds: int,
    ) -> DurableJobLease | None:
        """Lease one due canonical command without owning commit/rollback."""
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        if not isinstance(worker_id, str) or not worker_id:
            raise ValueError("worker_id is required")
        row = self._fetchone(
            "SELECT job_id, command_identity, command_type, command_version, "
            "command_payload, submitted_by, correlation_id, attempt_count, max_attempts "
            "FROM background_jobs WHERE status = 'queued' AND command_type IS NOT NULL "
            "AND available_at <= CURRENT_TIMESTAMP(6) ORDER BY created_at "
            "LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        if row is None:
            return None
        command = _canonical_command_from_row(row)
        lease_token = str(uuid.uuid4())
        updated = self._execute(
            "UPDATE background_jobs SET status = 'running', attempt_count = attempt_count + 1, "
            "lease_token = %s, lease_owner = %s, "
            "lease_expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s SECOND) "
            "WHERE job_id = %s AND status = 'queued'",
            (lease_token, worker_id, lease_seconds, command.job_id),
        )
        if updated != 1:
            raise DurableJobStateConflict("job was claimed by another worker")
        return DurableJobLease(
            command.job_id,
            lease_token,
            command,
            int(_value(row, "attempt_count", 7)) + 1,
        )

    def complete_canonical_claim(
        self,
        lease: DurableJobLease,
        outcome: DurableJobSuccessOutcome,
    ) -> None:
        self._transition_canonical_claim(lease, "succeeded", outcome, None, 0)

    def fail_canonical_claim(
        self,
        lease: DurableJobLease,
        outcome: DurableJobFailureOutcome,
        retry_after_seconds: int | None = None,
    ) -> None:
        if retry_after_seconds is not None and lease.attempt_count < lease.command.max_attempts:
            self._transition_canonical_claim(lease, "queued", None, outcome, retry_after_seconds)
            return
        self._transition_canonical_claim(lease, "failed", None, outcome, 0)

    def _transition_canonical_claim(
        self,
        lease: DurableJobLease,
        status: str,
        success: DurableJobSuccessOutcome | None,
        failure: DurableJobFailureOutcome | None,
        delay_seconds: int,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must not be negative")
        receipt_payload = None if success is None else _closed_payload_json(success.to_payload())
        error_payload = None if failure is None else _closed_payload_json(failure.to_payload())
        result_reference = None if success is None else success.result_reference
        updated = self._execute(
            "UPDATE background_jobs SET status = %s, receipt_payload = %s, error_payload = %s, "
            "result_reference = %s, lease_token = NULL, lease_owner = NULL, lease_expires_at = NULL, "
            "available_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s SECOND), "
            "completed_at = CASE WHEN %s = 'queued' THEN NULL ELSE CURRENT_TIMESTAMP(6) END "
            "WHERE job_id = %s AND status = 'running' AND lease_token = %s",
            (
                status,
                receipt_payload,
                error_payload,
                result_reference,
                delay_seconds,
                status,
                lease.job_id,
                lease.lease_token,
            ),
        )
        if updated != 1:
            raise DurableJobStateConflict("job lease is no longer held")

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


def _canonical_command_from_row(row: Any) -> DurableJobCommand:
    values = {
        "job_id": _value(row, "job_id", 0),
        "command_identity": _value(row, "command_identity", 1),
        "command_type": _value(row, "command_type", 2),
        "command_version": _value(row, "command_version", 3),
        "command_payload": _value(row, "command_payload", 4),
        "submitted_by": _value(row, "submitted_by", 5),
        "correlation_id": _value(row, "correlation_id", 6),
        "max_attempts": _value(row, "max_attempts", 8),
    }
    if any(value is None for value in values.values()):
        raise DurableJobContractViolation("canonical durable command row contains NULL")
    if not all(isinstance(values[key], str) and values[key] for key in (
        "job_id", "command_identity", "command_type", "submitted_by", "correlation_id"
    )):
        raise DurableJobContractViolation("canonical durable command row contains invalid text")
    version = values["command_version"]
    max_attempts = values["max_attempts"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise DurableJobContractViolation("canonical durable command row contains invalid version")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise DurableJobContractViolation("canonical durable command row contains invalid max attempts")
    validate_command_key(values["command_identity"])
    payload = parse_canonical_payload(values["command_payload"])
    equality_for(values["command_type"], version, payload, values["submitted_by"])
    return DurableJobCommand(
        values["job_id"],
        values["command_identity"],
        values["command_type"],
        version,
        payload,
        values["submitted_by"],
        values["correlation_id"],
        max_attempts,
    )


def _closed_payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

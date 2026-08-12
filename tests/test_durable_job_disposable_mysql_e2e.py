"""Durable job lifecycle proof that preserves records in the test database."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from infrastructure.mysql.background_job_repository import (
    BackgroundJobRepository,
    JobIdempotencyConflict,
)
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.durable_job_queue import DurableJobCommand, DurableJobStateConflict


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_durable_job_retries_once_and_persists_one_receipt():
    repository, connection = _repository()
    try:
        command = _command("retry")
        assert repository.enqueue_command(command) == command.job_id
        with pytest.raises(JobIdempotencyConflict) as duplicate:
            repository.enqueue_command(command)
        assert duplicate.value.job_id == command.job_id

        first_lease = repository.claim_next_command("verification-worker-a", 60)
        assert first_lease is not None
        assert first_lease.command.job_id == command.job_id
        repository.fail_claimed_job(
            first_lease,
            {"error": {"code": "temporary_unavailable"}},
            retry_after_seconds=0,
        )
        second_lease = repository.claim_next_command("verification-worker-b", 60)
        assert second_lease is not None
        assert second_lease.command.job_id == command.job_id
        assert second_lease.attempt_count == 2
        repository.complete_claimed_job(
            second_lease,
            {"result": "verified"},
            "verification-receipt",
        )

        stored = repository.get_job(command.job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.receipt_payload == {"result": "verified"}
        assert stored.result_reference == "verification-receipt"
    finally:
        connection.close()


def test_durable_job_cancellation_rejects_a_claimed_command():
    repository, connection = _repository()
    try:
        command = _command("cancel")
        repository.enqueue_command(command)
        repository.cancel_queued_job(command.job_id)
        assert repository.get_job(command.job_id).status == "cancelled"

        claimed_command = _command("claimed-cancel")
        repository.enqueue_command(claimed_command)
        lease = repository.claim_next_command("verification-worker-c", 60)
        assert lease is not None
        assert lease.command.job_id == claimed_command.job_id
        with pytest.raises(DurableJobStateConflict):
            repository.cancel_queued_job(claimed_command.job_id)
        repository.fail_claimed_job(lease, {"error": {"code": "test_cleanup"}})
    finally:
        connection.close()


def _repository() -> tuple[BackgroundJobRepository, object]:
    connection = get_connection()
    return BackgroundJobRepository(connection), connection


def _command(label: str) -> DurableJobCommand:
    identity = f"verification-job-{label}-{uuid4().hex}"
    return DurableJobCommand(
        job_id=identity,
        command_identity=identity,
        command_type="verification.durable_job",
        command_version=1,
        payload={"label": label},
        submitted_by="verification-runner",
        correlation_id=identity,
        max_attempts=2,
    )

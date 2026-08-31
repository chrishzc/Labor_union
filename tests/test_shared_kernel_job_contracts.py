"""Regression contracts for shared background and durable job primitives."""

import pytest

from shared_kernel.background_jobs import (
    BackgroundJobAccepted,
    BackgroundJobIdentity,
    BackgroundJobRecord,
    BackgroundJobStatus,
    transition_background_job,
)
from shared_kernel.durable_job_queue import (
    DurableJobCommand,
    RetryableDurableJobError,
    TerminalDurableJobError,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.performance import SingleFlightCommandIdentity


def _background_job_identity() -> BackgroundJobIdentity:
    return BackgroundJobIdentity(
        job_id="job-001",
        command_identity=SingleFlightCommandIdentity(
            IdempotencyKey("orders:123:cancel:v1"),
            fingerprint_payload({"order_id": 123, "action": "cancel"}),
        ),
        correlation_id=CorrelationId("corr-001"),
    )


def test_background_job_state_machine_allows_only_explicit_transitions():
    assert transition_background_job(
        BackgroundJobStatus.QUEUED,
        BackgroundJobStatus.RUNNING,
    ) is BackgroundJobStatus.RUNNING
    assert transition_background_job(
        BackgroundJobStatus.QUEUED,
        BackgroundJobStatus.CANCELLED,
    ) is BackgroundJobStatus.CANCELLED
    assert transition_background_job(
        BackgroundJobStatus.RUNNING,
        BackgroundJobStatus.SUCCEEDED,
    ) is BackgroundJobStatus.SUCCEEDED
    assert transition_background_job(
        BackgroundJobStatus.RUNNING,
        BackgroundJobStatus.FAILED,
    ) is BackgroundJobStatus.FAILED
    assert transition_background_job(
        BackgroundJobStatus.SUCCEEDED,
        BackgroundJobStatus.SUCCEEDED,
    ) is BackgroundJobStatus.SUCCEEDED

    with pytest.raises(ValueError, match="transition is not allowed"):
        transition_background_job(
            BackgroundJobStatus.QUEUED,
            BackgroundJobStatus.SUCCEEDED,
        )
    with pytest.raises(ValueError, match="transition is not allowed"):
        transition_background_job(
            BackgroundJobStatus.SUCCEEDED,
            BackgroundJobStatus.RUNNING,
        )


def test_background_job_acceptance_must_start_queued_with_positive_retry():
    identity = _background_job_identity()
    accepted = BackgroundJobAccepted(identity, "/jobs/job-001", 3)

    assert accepted.status is BackgroundJobStatus.QUEUED
    assert accepted.retry_after_seconds == 3

    with pytest.raises(ValueError, match="positive integer"):
        BackgroundJobAccepted(identity, "/jobs/job-001", 0)
    with pytest.raises(ValueError, match="must be queued"):
        BackgroundJobAccepted(
            identity,
            "/jobs/job-001",
            3,
            status=BackgroundJobStatus.RUNNING,
        )


def test_background_job_record_enforces_terminal_result_shape():
    identity = _background_job_identity()

    succeeded = BackgroundJobRecord(
        identity,
        BackgroundJobStatus.SUCCEEDED,
        result_reference="receipt-001",
    )
    failed = BackgroundJobRecord(
        identity,
        BackgroundJobStatus.FAILED,
        error_code="provider_unavailable",
    )

    assert succeeded.result_reference == "receipt-001"
    assert failed.error_code == "provider_unavailable"

    with pytest.raises(ValueError, match="cannot have an error"):
        BackgroundJobRecord(
            identity,
            BackgroundJobStatus.SUCCEEDED,
            result_reference="receipt-001",
            error_code="unexpected",
        )
    with pytest.raises(ValueError, match="cannot have a result"):
        BackgroundJobRecord(
            identity,
            BackgroundJobStatus.FAILED,
            result_reference="receipt-001",
            error_code="failed",
        )
    with pytest.raises(ValueError, match="unfinished job"):
        BackgroundJobRecord(
            identity,
            BackgroundJobStatus.RUNNING,
            result_reference="too-early",
        )


def test_durable_job_command_requires_identity_and_positive_limits():
    command = DurableJobCommand(
        job_id="job-001",
        command_identity="orders:123:cancel:v1",
        command_type="orders.cancel",
        command_version=1,
        payload={"order_id": 123},
        submitted_by="operator-1",
        correlation_id="corr-001",
    )

    assert command.max_attempts == 3
    assert command.payload == {"order_id": 123}

    with pytest.raises(ValueError, match="identity is required"):
        DurableJobCommand(
            job_id="",
            command_identity="orders:123:cancel:v1",
            command_type="orders.cancel",
            command_version=1,
            payload={},
            submitted_by="operator-1",
            correlation_id="corr-001",
        )
    with pytest.raises(ValueError, match="must be positive"):
        DurableJobCommand(
            job_id="job-001",
            command_identity="orders:123:cancel:v1",
            command_type="orders.cancel",
            command_version=0,
            payload={},
            submitted_by="operator-1",
            correlation_id="corr-001",
        )
    with pytest.raises(ValueError, match="must be positive"):
        DurableJobCommand(
            job_id="job-001",
            command_identity="orders:123:cancel:v1",
            command_type="orders.cancel",
            command_version=1,
            payload={},
            submitted_by="operator-1",
            correlation_id="corr-001",
            max_attempts=0,
        )


def test_retryable_durable_job_error_preserves_machine_readable_code():
    error = RetryableDurableJobError(
        "provider_timeout",
        "provider request timed out",
    )

    assert error.code == "provider_timeout"
    assert error.message == "provider request timed out"
    assert str(error) == "provider request timed out"


def test_terminal_durable_job_error_preserves_typed_domain_error():
    typed_error = TypedError(
        ErrorCategory.CONFLICT,
        "version_conflict",
        "current facts changed",
        CorrelationId("corr-001"),
    )

    raised = TerminalDurableJobError(typed_error)

    assert raised.error is typed_error
    assert str(raised) == "current facts changed"

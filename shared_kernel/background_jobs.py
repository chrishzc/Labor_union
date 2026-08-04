"""Durable background-job contracts and lifecycle policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from shared_kernel.identities import CorrelationId
from shared_kernel.performance import SingleFlightCommandIdentity
from shared_kernel.validation import (
    require_canonical_text,
    require_positive_integer,
)

_JOB_IDENTITY_MAXIMUM_LENGTH = 191
_STATUS_URL_MAXIMUM_LENGTH = 500


class BackgroundJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS = {
    BackgroundJobStatus.QUEUED: frozenset(
        {BackgroundJobStatus.RUNNING, BackgroundJobStatus.CANCELLED}
    ),
    BackgroundJobStatus.RUNNING: frozenset(
        {BackgroundJobStatus.SUCCEEDED, BackgroundJobStatus.FAILED}
    ),
    BackgroundJobStatus.SUCCEEDED: frozenset(),
    BackgroundJobStatus.FAILED: frozenset(),
    BackgroundJobStatus.CANCELLED: frozenset(),
}


def transition_background_job(
    current_status: BackgroundJobStatus,
    target_status: BackgroundJobStatus,
) -> BackgroundJobStatus:
    if current_status is target_status:
        return current_status
    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise ValueError("background job transition is not allowed")
    return target_status


@dataclass(frozen=True, slots=True)
class BackgroundJobIdentity:
    job_id: str
    command_identity: SingleFlightCommandIdentity
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(
            self.job_id,
            "job id",
            _JOB_IDENTITY_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class BackgroundJobAccepted:
    identity: BackgroundJobIdentity
    status_url: str
    retry_after_seconds: int
    status: BackgroundJobStatus = BackgroundJobStatus.QUEUED

    def __post_init__(self) -> None:
        require_canonical_text(
            self.status_url,
            "status URL",
            _STATUS_URL_MAXIMUM_LENGTH,
        )
        require_positive_integer(self.retry_after_seconds, "retry after seconds")
        if self.status is not BackgroundJobStatus.QUEUED:
            raise ValueError("accepted background job must be queued")


@dataclass(frozen=True, slots=True)
class BackgroundJobRecord:
    identity: BackgroundJobIdentity
    status: BackgroundJobStatus
    result_reference: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status is BackgroundJobStatus.SUCCEEDED:
            _validate_succeeded_job(self)
            return
        if self.status is BackgroundJobStatus.FAILED:
            _validate_failed_job(self)
            return
        if self.result_reference is not None or self.error_code is not None:
            raise ValueError("unfinished job cannot have a result or error")


def _validate_succeeded_job(record: BackgroundJobRecord) -> None:
    if record.error_code is not None:
        raise ValueError("succeeded job cannot have an error")
    require_canonical_text(
        record.result_reference,
        "job result reference",
        _JOB_IDENTITY_MAXIMUM_LENGTH,
    )


def _validate_failed_job(record: BackgroundJobRecord) -> None:
    if record.result_reference is not None:
        raise ValueError("failed job cannot have a result")
    require_canonical_text(
        record.error_code,
        "job error code",
        _JOB_IDENTITY_MAXIMUM_LENGTH,
    )


class BackgroundJobRepository(Protocol):
    def get(self, job_id: str) -> BackgroundJobRecord | None: ...

    def save(self, record: BackgroundJobRecord) -> None: ...


class BackgroundJobQueuePort(Protocol):
    def enqueue(self, identity: BackgroundJobIdentity) -> None: ...

"""Typed durable-command envelope and queue lifecycle contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared_kernel.errors import TypedError


@dataclass(frozen=True, slots=True)
class DurableJobCommand:
    job_id: str
    command_identity: str
    command_type: str
    command_version: int
    payload: dict[str, Any]
    submitted_by: str
    correlation_id: str
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not all((self.job_id, self.command_identity, self.command_type)):
            raise ValueError("durable command identity is required")
        if self.command_version < 1 or self.max_attempts < 1:
            raise ValueError("durable command version and attempts must be positive")


@dataclass(frozen=True, slots=True)
class DurableJobLease:
    job_id: str
    lease_token: str
    command: DurableJobCommand
    attempt_count: int


class DurableJobStateConflict(Exception):
    """A requested queue transition no longer owns the job state."""


class RetryableDurableJobError(Exception):
    """A handler failure that should return the command to the queue."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class TerminalDurableJobError(Exception):
    """A domain command was rejected and must remain queryable as a failed job."""

    def __init__(self, error: TypedError):
        self.error = error
        super().__init__(error.message)

"""Typed application contracts for durable LINE delivery tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.delivery import (
    LineAttemptPlan,
    LineDeliveryAttemptOutcome,
    LineDeliveryLease,
    LineDeliveryRequest,
    LineDeliveryStatus,
    LineDeliveryTaskSnapshot,
)
from domains.line.identities import LineDeliveryTaskId, LineProviderMessageId
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_LEASE_OWNER_MAXIMUM_LENGTH = 191
_PROVIDER_ERROR_MAXIMUM_LENGTH = 500
_MAXIMUM_CLAIM_BATCH_SIZE = 100


class LineDeliveryCommandOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


class LineProviderOutcomeType(StrEnum):
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class EnqueueLineDeliveryCommand:
    request: LineDeliveryRequest


@dataclass(frozen=True, slots=True)
class EnqueueLineDeliveryResult:
    outcome: LineDeliveryCommandOutcome
    task_id: LineDeliveryTaskId
    status: LineDeliveryStatus


@dataclass(frozen=True, slots=True)
class ClaimLineDeliveryTasksQuery:
    lease_owner: str
    now: datetime
    batch_size: int = 25

    def __post_init__(self) -> None:
        require_canonical_text(
            self.lease_owner,
            "LINE delivery lease owner",
            _LEASE_OWNER_MAXIMUM_LENGTH,
        )
        _require_aware_datetime(self.now)
        require_positive_integer(self.batch_size, "LINE delivery batch size")
        if self.batch_size > _MAXIMUM_CLAIM_BATCH_SIZE:
            raise ValueError("LINE delivery batch size exceeds maximum")


@dataclass(frozen=True, slots=True)
class LineProviderOutcome:
    outcome_type: LineProviderOutcomeType
    provider_message_id: LineProviderMessageId | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        _validate_provider_outcome(self)


@dataclass(frozen=True, slots=True)
class RecordLineDeliveryAttemptCommand:
    task: LineDeliveryTaskSnapshot
    lease: LineDeliveryLease
    provider_outcome: LineProviderOutcome
    completed_at: datetime
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        if self.task.task_id != self.lease.task_id:
            raise ValueError("LINE attempt lease does not belong to the task")
        _require_aware_datetime(self.completed_at)


@dataclass(frozen=True, slots=True)
class RecordLineDeliveryAttemptResult:
    task_id: LineDeliveryTaskId
    plan: LineAttemptPlan


@dataclass(frozen=True, slots=True)
class CancelLineDeliveryTaskCommand:
    task_id: LineDeliveryTaskId
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


def provider_attempt_outcome(
    provider_outcome: LineProviderOutcome,
) -> LineDeliveryAttemptOutcome:
    if provider_outcome.outcome_type is LineProviderOutcomeType.SUCCESS:
        return LineDeliveryAttemptOutcome.SUCCESS
    if provider_outcome.outcome_type is LineProviderOutcomeType.REJECTED:
        return LineDeliveryAttemptOutcome.TERMINAL_FAILURE
    return LineDeliveryAttemptOutcome.RETRYABLE_FAILURE


def _validate_provider_outcome(outcome: LineProviderOutcome) -> None:
    if not isinstance(outcome.outcome_type, LineProviderOutcomeType):
        raise TypeError("LINE provider outcome type is invalid")
    if outcome.outcome_type is LineProviderOutcomeType.SUCCESS:
        _validate_successful_provider_outcome(outcome)
        return
    _validate_failed_provider_outcome(outcome)


def _validate_successful_provider_outcome(outcome: LineProviderOutcome) -> None:
    if outcome.provider_message_id is None:
        raise ValueError("successful LINE delivery requires provider message ID")
    error_details = (
        outcome.error_code,
        outcome.error_message,
        outcome.retry_after_seconds,
    )
    if any(value is not None for value in error_details):
        raise ValueError("successful LINE delivery cannot contain error details")


def _validate_failed_provider_outcome(outcome: LineProviderOutcome) -> None:
    if outcome.provider_message_id is not None:
        raise ValueError("failed LINE delivery cannot contain provider message ID")
    if outcome.error_code is None or outcome.error_message is None:
        raise ValueError("failed LINE delivery requires provider error details")
    require_canonical_text(outcome.error_code, "LINE provider error code", 191)
    require_canonical_text(
        outcome.error_message,
        "LINE provider error message",
        _PROVIDER_ERROR_MAXIMUM_LENGTH,
    )
    if outcome.retry_after_seconds is not None:
        require_nonnegative_integer(
            outcome.retry_after_seconds,
            "LINE provider retry-after seconds",
        )


def _require_aware_datetime(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("LINE delivery time must be timezone-aware")
    if value.utcoffset() is None:
        raise ValueError("LINE delivery time must have a UTC offset")
    return value


__all__ = [
    "CancelLineDeliveryTaskCommand",
    "ClaimLineDeliveryTasksQuery",
    "EnqueueLineDeliveryCommand",
    "EnqueueLineDeliveryResult",
    "LineDeliveryCommandOutcome",
    "LineProviderOutcome",
    "LineProviderOutcomeType",
    "RecordLineDeliveryAttemptCommand",
    "RecordLineDeliveryAttemptResult",
    "provider_attempt_outcome",
]

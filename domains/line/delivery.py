"""Pure LINE delivery task, lease, retry, and transition rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from domains.line.canonical_payload import validate_canonical_line_payload_json
from domains.line.identities import (
    LineDeliveryTaskId,
    LineGroupId,
    LineRoomId,
    LineUserId,
)
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_AGGREGATE_REFERENCE_MAXIMUM_LENGTH = 191
_LEASE_OWNER_MAXIMUM_LENGTH = 191


class LineRecipientType(StrEnum):
    USER = "user"
    GROUP = "group"
    ROOM = "room"


class LineMessageKind(StrEnum):
    TEXT = "text"
    FLEX = "flex"


class LineDeliveryStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    RETRYABLE_FAILED = "retryable_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LineDeliveryAttemptOutcome(StrEnum):
    SUCCESS = "success"
    RETRYABLE_FAILURE = "retryable_failure"
    TERMINAL_FAILURE = "terminal_failure"


_ALLOWED_DELIVERY_TRANSITIONS = {
    LineDeliveryStatus.PENDING: {
        LineDeliveryStatus.PROCESSING,
        LineDeliveryStatus.CANCELLED,
    },
    LineDeliveryStatus.PROCESSING: {
        LineDeliveryStatus.SENT,
        LineDeliveryStatus.RETRYABLE_FAILED,
        LineDeliveryStatus.FAILED,
    },
    LineDeliveryStatus.RETRYABLE_FAILED: {
        LineDeliveryStatus.PENDING,
        LineDeliveryStatus.CANCELLED,
    },
}


class LineDeliveryStateConflict(ValueError):
    """Raised when a delivery task attempts an invalid transition."""


@dataclass(frozen=True, slots=True)
class LineRecipient:
    recipient_type: LineRecipientType
    identity: LineUserId | LineGroupId | LineRoomId

    def __post_init__(self) -> None:
        expected_type = {
            LineRecipientType.USER: LineUserId,
            LineRecipientType.GROUP: LineGroupId,
            LineRecipientType.ROOM: LineRoomId,
        }.get(self.recipient_type)
        if expected_type is None or not isinstance(self.identity, expected_type):
            raise TypeError("LINE recipient type and identity do not match")


@dataclass(frozen=True, slots=True)
class LineDeliveryRequest:
    recipient: LineRecipient
    message_kind: LineMessageKind
    payload_json: str
    scheduled_at: datetime
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    source_aggregate_type: str
    source_aggregate_identity: str

    def __post_init__(self) -> None:
        if not isinstance(self.message_kind, LineMessageKind):
            raise TypeError("LINE message kind is invalid")
        validate_canonical_line_payload_json(self.payload_json)
        _require_aware_datetime(self.scheduled_at, "LINE scheduled_at")
        _validate_source_aggregate(self)

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {
                "recipient_type": self.recipient.recipient_type.value,
                "recipient_identity": self.recipient.identity.value,
                "message_kind": self.message_kind.value,
                "payload_json": self.payload_json,
                "scheduled_at": self.scheduled_at.astimezone(timezone.utc).isoformat(),
                "source_aggregate_type": self.source_aggregate_type,
                "source_aggregate_identity": self.source_aggregate_identity,
            }
        )


@dataclass(frozen=True, slots=True)
class LineDeliveryTaskSnapshot:
    task_id: LineDeliveryTaskId
    request: LineDeliveryRequest
    status: LineDeliveryStatus
    completed_attempts: int
    lease: LineDeliveryLease | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LineDeliveryStatus):
            raise TypeError("LINE delivery task status is invalid")
        require_nonnegative_integer(
            self.completed_attempts,
            "completed LINE attempts",
        )


@dataclass(frozen=True, slots=True)
class LineDeliveryLease:
    task_id: LineDeliveryTaskId
    owner: str
    acquired_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        require_canonical_text(self.owner, "LINE lease owner", _LEASE_OWNER_MAXIMUM_LENGTH)
        _require_aware_datetime(self.acquired_at, "LINE lease acquired_at")
        _require_aware_datetime(self.expires_at, "LINE lease expires_at")
        if self.expires_at <= self.acquired_at:
            raise ValueError("LINE lease expiry must be after acquisition")


@dataclass(frozen=True, slots=True)
class LineRetryPolicy:
    maximum_attempts: int
    base_delay_seconds: int
    maximum_delay_seconds: int

    def __post_init__(self) -> None:
        require_positive_integer(self.maximum_attempts, "LINE maximum attempts")
        require_positive_integer(self.base_delay_seconds, "LINE base retry delay")
        require_positive_integer(self.maximum_delay_seconds, "LINE maximum retry delay")
        if self.maximum_delay_seconds < self.base_delay_seconds:
            raise ValueError("LINE maximum retry delay cannot be below base delay")


@dataclass(frozen=True, slots=True)
class LineAttemptPlan:
    resulting_status: LineDeliveryStatus
    next_attempt_at: datetime | None


def transition_delivery_status(
    current: LineDeliveryStatus,
    target: LineDeliveryStatus,
) -> LineDeliveryStatus:
    if not isinstance(current, LineDeliveryStatus):
        raise TypeError("current LINE delivery status is invalid")
    if target not in _ALLOWED_DELIVERY_TRANSITIONS.get(current, set()):
        raise LineDeliveryStateConflict(
            f"cannot transition LINE delivery from {current.value} to {target.value}"
        )
    return target


def plan_delivery_attempt(
    policy: LineRetryPolicy,
    *,
    completed_attempts: int,
    outcome: LineDeliveryAttemptOutcome,
    completed_at: datetime,
    retry_after_seconds: int | None = None,
) -> LineAttemptPlan:
    require_positive_integer(completed_attempts, "completed LINE attempts")
    _require_aware_datetime(completed_at, "LINE attempt completed_at")
    if outcome is LineDeliveryAttemptOutcome.SUCCESS:
        return LineAttemptPlan(LineDeliveryStatus.SENT, None)
    if outcome is LineDeliveryAttemptOutcome.TERMINAL_FAILURE:
        return LineAttemptPlan(LineDeliveryStatus.FAILED, None)
    return _retryable_attempt_plan(
        policy,
        completed_attempts,
        completed_at,
        retry_after_seconds,
    )


def lease_is_active(lease: LineDeliveryLease, now: datetime) -> bool:
    _require_aware_datetime(now, "LINE lease comparison time")
    return lease.acquired_at <= now < lease.expires_at


def _retryable_attempt_plan(
    policy: LineRetryPolicy,
    completed_attempts: int,
    completed_at: datetime,
    retry_after_seconds: int | None,
) -> LineAttemptPlan:
    if completed_attempts >= policy.maximum_attempts:
        return LineAttemptPlan(LineDeliveryStatus.FAILED, None)
    delay_seconds = _retry_delay_seconds(
        policy,
        completed_attempts,
        retry_after_seconds,
    )
    return LineAttemptPlan(
        LineDeliveryStatus.RETRYABLE_FAILED,
        completed_at + timedelta(seconds=delay_seconds),
    )


def _retry_delay_seconds(
    policy: LineRetryPolicy,
    completed_attempts: int,
    retry_after_seconds: int | None,
) -> int:
    exponential_delay = min(
        policy.base_delay_seconds * (2 ** (completed_attempts - 1)),
        policy.maximum_delay_seconds,
    )
    if retry_after_seconds is None:
        return exponential_delay
    require_nonnegative_integer(retry_after_seconds, "LINE retry-after seconds")
    return max(exponential_delay, retry_after_seconds)


def _validate_source_aggregate(request: LineDeliveryRequest) -> None:
    require_canonical_text(
        request.source_aggregate_type,
        "LINE source aggregate type",
        _AGGREGATE_REFERENCE_MAXIMUM_LENGTH,
    )
    require_canonical_text(
        request.source_aggregate_identity,
        "LINE source aggregate identity",
        _AGGREGATE_REFERENCE_MAXIMUM_LENGTH,
    )


def _require_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() is None:
        raise ValueError(f"{field_name} must have a UTC offset")
    return value


__all__ = [
    "LineAttemptPlan",
    "LineDeliveryAttemptOutcome",
    "LineDeliveryLease",
    "LineDeliveryRequest",
    "LineDeliveryStateConflict",
    "LineDeliveryStatus",
    "LineDeliveryTaskSnapshot",
    "LineMessageKind",
    "LineRecipient",
    "LineRecipientType",
    "LineRetryPolicy",
    "lease_is_active",
    "plan_delivery_attempt",
    "transition_delivery_status",
]

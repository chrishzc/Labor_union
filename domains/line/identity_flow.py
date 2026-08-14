"""Pure one-use LIFF identity-flow state and validation rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineIdentityFlowId, LineUserId


class LineIdentityFlowPurpose(StrEnum):
    CUSTOMER_BINDING = "customer_binding"
    STAFF_VERIFICATION = "staff_verification"
    ADMIN_BINDING = "admin_binding"
    STAFF_SELF_SERVICE = "staff_self_service"


class LineIdentityFlowStatus(StrEnum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class LineIdentityFlowConflict(ValueError):
    """Raised when a LIFF identity flow is invalid, stale, or replayed."""


@dataclass(frozen=True, slots=True)
class LineIdentityFlowSnapshot:
    flow_id: LineIdentityFlowId
    purpose: LineIdentityFlowPurpose
    line_user_id: LineUserId
    status: LineIdentityFlowStatus
    expires_at: datetime
    idempotency_key: str
    attempt_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, LineIdentityFlowPurpose):
            raise TypeError("LINE identity flow purpose is invalid")
        if not isinstance(self.status, LineIdentityFlowStatus):
            raise TypeError("LINE identity flow status is invalid")
        _require_aware_datetime(self.expires_at)
        if not self.idempotency_key.strip():
            raise ValueError("LINE identity flow idempotency key is required")
        if self.attempt_count < 0:
            raise ValueError("LINE identity flow attempts cannot be negative")


def validate_identity_flow(
    snapshot: LineIdentityFlowSnapshot,
    *,
    purpose: LineIdentityFlowPurpose,
    line_user_id: LineUserId,
    now: datetime,
) -> None:
    _require_aware_datetime(now)
    if snapshot.purpose is not purpose:
        raise LineIdentityFlowConflict("LINE identity flow purpose does not match")
    if snapshot.line_user_id != line_user_id:
        raise LineIdentityFlowConflict("LINE identity flow belongs to another user")
    if snapshot.status is not LineIdentityFlowStatus.ACTIVE:
        raise LineIdentityFlowConflict("LINE identity flow is no longer active")
    if snapshot.expires_at <= now:
        raise LineIdentityFlowConflict("LINE identity flow has expired")


def _require_aware_datetime(value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("LINE identity flow time must be timezone-aware")
    if value.utcoffset() is None:
        raise ValueError("LINE identity flow time must have a UTC offset")


__all__ = [
    "LineIdentityFlowConflict",
    "LineIdentityFlowPurpose",
    "LineIdentityFlowSnapshot",
    "LineIdentityFlowStatus",
    "validate_identity_flow",
]

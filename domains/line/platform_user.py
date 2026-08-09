"""Pure LINE friend-state transitions for platform user identities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineUserId, LineWebhookEventId
from shared_kernel.identities import ExpectedVersion


class LineFriendStatus(StrEnum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    BLOCKED = "blocked"


class LineFriendEventType(StrEnum):
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    ACTIVITY = "activity"


@dataclass(frozen=True, slots=True)
class LineFriendEvent:
    line_user_id: LineUserId
    event_id: LineWebhookEventId
    event_type: LineFriendEventType
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, LineFriendEventType):
            raise TypeError("LINE friend event type is invalid")
        _require_aware_datetime(self.occurred_at)


@dataclass(frozen=True, slots=True)
class LinePlatformUserSnapshot:
    line_user_id: LineUserId
    friend_status: LineFriendStatus
    version: ExpectedVersion
    first_followed_at: datetime | None = None
    last_followed_at: datetime | None = None
    blocked_at: datetime | None = None
    last_event_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.friend_status, LineFriendStatus):
            raise TypeError("LINE friend status is invalid")
        for value in (
            self.first_followed_at,
            self.last_followed_at,
            self.blocked_at,
            self.last_event_at,
        ):
            if value is not None:
                _require_aware_datetime(value)


def friend_status_for_event(event_type: LineFriendEventType) -> LineFriendStatus:
    if event_type is LineFriendEventType.FOLLOW:
        return LineFriendStatus.ACTIVE
    if event_type is LineFriendEventType.ACTIVITY:
        return LineFriendStatus.ACTIVE
    if event_type is LineFriendEventType.UNFOLLOW:
        return LineFriendStatus.BLOCKED
    raise TypeError("LINE friend event type is invalid")


def _require_aware_datetime(value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("LINE friend event time must be timezone-aware")
    if value.utcoffset() is None:
        raise ValueError("LINE friend event time must have a UTC offset")


__all__ = [
    "LineFriendEvent",
    "LineFriendEventType",
    "LineFriendStatus",
    "LinePlatformUserSnapshot",
    "friend_status_for_event",
]

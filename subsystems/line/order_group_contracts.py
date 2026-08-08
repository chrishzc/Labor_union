"""Typed application contracts for order-group binding and invitation relay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineGroupId, LineUserId
from domains.line.order_group import (
    LineGroupInvitationRelay,
    LineOrderGroupBindingCandidate,
    LineOrderGroupBindingSnapshot,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_positive_integer

_CASE_NUMBER_MAXIMUM_LENGTH = 50


class LineOrderGroupCommandOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class GetLineOrderGroupQuery:
    case_no: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class BindLineOrderGroupCommand:
    case_no: str
    group_id: LineGroupId
    expected_version: ExpectedVersion
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class BindLineOrderGroupResult:
    outcome: LineOrderGroupCommandOutcome
    candidate: LineOrderGroupBindingCandidate


@dataclass(frozen=True, slots=True)
class RelayLineGroupInvitationCommand:
    relay: LineGroupInvitationRelay
    idempotency_key: IdempotencyKey


@dataclass(frozen=True, slots=True)
class RelayLineGroupInvitationResult:
    outcome: LineOrderGroupCommandOutcome
    accepted_recipient_count: int

    def __post_init__(self) -> None:
        require_positive_integer(
            self.accepted_recipient_count,
            "LINE invitation accepted recipient count",
        )


@dataclass(frozen=True, slots=True)
class LineOrderGroupQueryResult:
    binding: LineOrderGroupBindingSnapshot


@dataclass(frozen=True, slots=True)
class OrderLineAudience:
    case_no: str
    customer_line_user_id: LineUserId
    staff_line_user_ids: tuple[LineUserId, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        values = tuple(item.value for item in self.staff_line_user_ids)
        if values != tuple(sorted(set(values))):
            raise ValueError("order staff LINE user IDs must be sorted and unique")


@dataclass(frozen=True, slots=True)
class LinkedLineAdmin:
    admin_user_id: int
    display_name: str
    role: str
    line_user_id: LineUserId

    def __post_init__(self) -> None:
        require_positive_integer(self.admin_user_id, "linked LINE admin user ID")
        require_canonical_text(self.display_name, "linked LINE admin name", 100)
        require_canonical_text(self.role, "linked LINE admin role", 50)


@dataclass(frozen=True, slots=True)
class LineOrderGroupEventRecord:
    event_id: int
    case_no: str
    event_type: str
    actor_id: str
    occurred_at: datetime
    invitation_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class LineOrderGroupPage:
    items: tuple[LineOrderGroupBindingSnapshot, ...]
    total: int


__all__ = [
    "BindLineOrderGroupCommand",
    "BindLineOrderGroupResult",
    "GetLineOrderGroupQuery",
    "LineOrderGroupCommandOutcome",
    "LineOrderGroupEventRecord",
    "LineOrderGroupPage",
    "LineOrderGroupQueryResult",
    "LinkedLineAdmin",
    "OrderLineAudience",
    "RelayLineGroupInvitationCommand",
    "RelayLineGroupInvitationResult",
]

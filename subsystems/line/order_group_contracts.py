"""Typed application contracts for order-group binding and invitation relay."""

from __future__ import annotations

from dataclasses import dataclass
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


__all__ = [
    "BindLineOrderGroupCommand",
    "BindLineOrderGroupResult",
    "GetLineOrderGroupQuery",
    "LineOrderGroupCommandOutcome",
    "LineOrderGroupQueryResult",
    "OrderLineAudience",
    "RelayLineGroupInvitationCommand",
    "RelayLineGroupInvitationResult",
]

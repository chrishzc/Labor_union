"""
File: order_group_contracts.py
Description: 定義 LINE 訂單群組綁定、邀請與唯讀 numbered query 的 typed contracts。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal

from domains.line.identities import LineGroupId, LineUserId
from domains.line.order_group import (
    LineGroupInvitationRelay,
    LineOrderGroupBindingCandidate,
    LineOrderGroupBindingSnapshot,
    LineOrderGroupBindingStatus,
    validate_invitation_url,
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
class LineOrderGroupInvitationSettings:
    """Private command/worker data, excluded from the observation API."""

    binding: LineOrderGroupBindingSnapshot
    invitation_url: str | None = field(repr=False)

    def __post_init__(self) -> None:
        if self.invitation_url is not None:
            validate_invitation_url(self.invitation_url)


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
class PaidOrderGroupTodo:
    case_no: str
    deposit_amount_ntd: int


@dataclass(frozen=True, slots=True)
class PaidOrderGroupTodoPage:
    items: tuple[PaidOrderGroupTodo, ...]
    page: int
    page_size: int
    total: int
    total_pages: int


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


@dataclass(frozen=True, slots=True)
class LineOrderGroupNumberedPage:
    items: tuple[LineOrderGroupBindingSnapshot, ...]
    page: int
    page_size: int
    total: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class LineOrderGroupEventPage:
    items: tuple[LineOrderGroupEventRecord, ...]
    page: int
    page_size: int
    total: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class LineOrderGroupParticipant:
    role: Literal["customer", "staff"]
    name: str | None
    membership_status: Literal["joined", "left", "pending", "unknown"]
    staff_union_no: str | None = None


@dataclass(frozen=True, slots=True)
class LineOrderGroupWorkspaceEvent:
    event_key: str
    case_no: str
    event_type: str
    occurred_at: datetime
    participant_role: Literal["customer", "staff"] | None = None
    participant_name: str | None = None
    participant_union_no: str | None = None


@dataclass(frozen=True, slots=True)
class LineOrderGroupWorkspaceRecord:
    case_no: str
    status: LineOrderGroupBindingStatus
    customer_name: str | None
    bound_at: datetime | None
    last_invitation_at: datetime | None
    members: tuple[LineOrderGroupParticipant, ...]
    latest_event: LineOrderGroupWorkspaceEvent | None


@dataclass(frozen=True, slots=True)
class LineOrderGroupWorkspacePage:
    items: tuple[LineOrderGroupWorkspaceRecord, ...]
    page: int
    page_size: int
    total: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class LineOrderGroupWorkspaceEventPage:
    items: tuple[LineOrderGroupWorkspaceEvent, ...]
    page: int
    page_size: int
    total: int
    total_pages: int


__all__ = [
    "PaidOrderGroupTodo",
    "PaidOrderGroupTodoPage",
    "BindLineOrderGroupCommand",
    "BindLineOrderGroupResult",
    "GetLineOrderGroupQuery",
    "LineOrderGroupCommandOutcome",
    "LineOrderGroupEventRecord",
    "LineOrderGroupEventPage",
    "LineOrderGroupNumberedPage",
    "LineOrderGroupPage",
    "LineOrderGroupQueryResult",
    "LineOrderGroupInvitationSettings",
    "LineOrderGroupParticipant",
    "LineOrderGroupWorkspaceEvent",
    "LineOrderGroupWorkspaceRecord",
    "LineOrderGroupWorkspacePage",
    "LineOrderGroupWorkspaceEventPage",
    "LinkedLineAdmin",
    "OrderLineAudience",
    "RelayLineGroupInvitationCommand",
    "RelayLineGroupInvitationResult",
]

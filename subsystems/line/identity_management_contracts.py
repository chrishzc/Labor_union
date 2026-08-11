"""Typed contracts for administrative LINE identity management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingStatus,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)


class LineIdentityRevocationStatus(StrEnum):
    PENDING_MENU_RESET = "pending_menu_reset"
    MENU_RESET_FAILED = "menu_reset_failed"
    COMPLETED = "completed"
    MANUAL_COMPLETED = "manual_completed"


@dataclass(frozen=True, slots=True)
class LineIdentityBindingListQuery:
    status: LineIdentityBindingStatus | None = LineIdentityBindingStatus.BOUND
    subject_type: LineBindingSubjectType | None = None
    search: str = ""
    page: int = 1
    page_size: int = 25


@dataclass(frozen=True, slots=True)
class LineIdentityBindingManagementView:
    line_user_id: str
    status: LineIdentityBindingStatus
    version: int
    subject_type: LineBindingSubjectType
    subject_reference: str
    subject_name: str
    updated_at: datetime | None
    revocation_request_id: int | None = None
    revocation_status: LineIdentityRevocationStatus | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LineIdentityBindingPage:
    items: tuple[LineIdentityBindingManagementView, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class LineIdentityRevocationPreview:
    binding: LineIdentityBindingManagementView
    default_menu_publication_id: int | None
    provider_menu_id: str | None
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LineIdentityReplacementPreview:
    binding: LineIdentityBindingManagementView
    target_subject_reference: str
    target_subject_name: str
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RequestLineIdentityRevocationCommand:
    line_user_id: LineUserId
    expected_version: ExpectedVersion
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ReplaceLineIdentitySubjectCommand:
    line_user_id: LineUserId
    expected_version: ExpectedVersion
    target_subject_reference: str
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class LineIdentityRevocationRequest:
    request_id: int
    line_user_id: LineUserId
    subject_type: LineBindingSubjectType
    subject_reference: str
    status: LineIdentityRevocationStatus
    requested_binding_version: ExpectedVersion
    pending_binding_version: ExpectedVersion
    publication_id: int
    provider_menu_id: str
    requested_by_actor_id: str
    reason: str
    idempotency_key: str
    correlation_id: str
    attempt_count: int
    last_error_code: str | None
    last_error_message: str | None


__all__ = [
    "LineIdentityBindingListQuery",
    "LineIdentityBindingManagementView",
    "LineIdentityBindingPage",
    "LineIdentityRevocationPreview",
    "LineIdentityReplacementPreview",
    "LineIdentityRevocationRequest",
    "LineIdentityRevocationStatus",
    "RequestLineIdentityRevocationCommand",
    "ReplaceLineIdentitySubjectCommand",
]

"""Typed application contracts for LINE identity claims and bindings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.line.identities import LineReviewRequestId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingStatus,
    LineIdentityClaim,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.validation import require_canonical_text


class LineIdentityCommandOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class SubmitLineIdentityClaimCommand:
    claim: LineIdentityClaim
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class SubmitLineIdentityClaimResult:
    outcome: LineIdentityCommandOutcome
    line_user_id: LineUserId
    binding_status: LineIdentityBindingStatus
    review_request_id: LineReviewRequestId | None


@dataclass(frozen=True, slots=True)
class BindAdminLineIdentityCommand:
    claim: LineIdentityClaim
    expected_version: ExpectedVersion
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        if self.claim.subject_type is not LineBindingSubjectType.ADMIN:
            raise ValueError("admin LINE binding requires an admin identity claim")


@dataclass(frozen=True, slots=True)
class BindAdminLineIdentityResult:
    outcome: LineIdentityCommandOutcome
    line_user_id: LineUserId
    resulting_version: ExpectedVersion


@dataclass(frozen=True, slots=True)
class LineIdentityLookupQuery:
    line_user_id: LineUserId


@dataclass(frozen=True, slots=True)
class LineIdentityCandidate:
    subject_type: LineBindingSubjectType
    subject_reference: str
    currently_bound_line_user_id: LineUserId | None = None

    def __post_init__(self) -> None:
        require_canonical_text(
            self.subject_reference,
            "LINE identity candidate reference",
            191,
        )


__all__ = [
    "BindAdminLineIdentityCommand",
    "BindAdminLineIdentityResult",
    "LineIdentityCommandOutcome",
    "LineIdentityCandidate",
    "LineIdentityLookupQuery",
    "SubmitLineIdentityClaimCommand",
    "SubmitLineIdentityClaimResult",
]

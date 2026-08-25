"""
File: identity_contracts.py
Description: 定義 LINE identity claim、Preview、Apply 與 binding 契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from domains.line.identities import LineIdentityFlowId, LineReviewRequestId, LineUserId
from domains.line.identity_flow import LineIdentityFlowPurpose
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
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.validation import require_canonical_text


class LineIdentityCommandOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


class LineIdentityPreviewStatus(StrEnum):
    AUTHENTICATION_PENDING = "authentication_pending"
    MATCHED = "matched"
    ALREADY_BOUND = "already_bound"
    REQUIRES_REVIEW = "requires_review"
    NOT_FOUND = "not_found"


class LineIdentityApplyStatus(StrEnum):
    BOUND = "bound"
    PENDING_REVIEW = "pending_review"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class CustomerIdentityProof:
    name: str
    phone: str

    def __post_init__(self) -> None:
        require_canonical_text(self.name, "customer name", 100)
        require_canonical_text(self.phone, "customer phone", 30)


@dataclass(frozen=True, slots=True)
class StaffIdentityProof:
    name: str
    identity_card: str
    birthday: date

    def __post_init__(self) -> None:
        require_canonical_text(self.name, "staff name", 100)
        require_canonical_text(self.identity_card, "staff identity card", 20)
        if not isinstance(self.birthday, date):
            raise TypeError("staff birthday is invalid")


@dataclass(frozen=True, slots=True)
class AdminCredentialProof:
    username: str
    password: str

    def __post_init__(self) -> None:
        require_canonical_text(self.username, "admin username", 100)
        require_canonical_text(self.password, "admin password", 256)


@dataclass(frozen=True, slots=True)
class OpenLineIdentityFlowCommand:
    purpose: LineIdentityFlowPurpose
    line_user_id: LineUserId
    expires_at: datetime
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class OpenLineIdentityFlowResult:
    flow_id: LineIdentityFlowId
    purpose: LineIdentityFlowPurpose
    line_user_id: LineUserId
    expires_at: datetime
    outcome: LineIdentityCommandOutcome


@dataclass(frozen=True, slots=True)
class LineIdentityPreview:
    status: LineIdentityPreviewStatus
    line_user_id: LineUserId
    candidate: LineIdentityCandidate | None
    expected_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class LineIdentityApplyResult:
    status: LineIdentityApplyStatus
    line_user_id: LineUserId
    subject_type: LineBindingSubjectType
    subject_reference: str
    review_request_id: LineReviewRequestId | None = None
    receipt_identity: str = ""


@dataclass(frozen=True, slots=True)
class VerifiedLiffIdentity:
    line_user_id: LineUserId
    audience: str
    expires_at: datetime

    def __post_init__(self) -> None:
        require_canonical_text(self.audience, "LIFF token audience", 191)
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("LIFF token expiry must be timezone-aware")


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
    "AdminCredentialProof",
    "CustomerIdentityProof",
    "LineIdentityPreview",
    "LineIdentityApplyResult",
    "LineIdentityApplyStatus",
    "LineIdentityPreviewStatus",
    "LineIdentityCommandOutcome",
    "LineIdentityCandidate",
    "LineIdentityLookupQuery",
    "OpenLineIdentityFlowCommand",
    "OpenLineIdentityFlowResult",
    "StaffIdentityProof",
    "VerifiedLiffIdentity",
    "SubmitLineIdentityClaimCommand",
    "SubmitLineIdentityClaimResult",
]

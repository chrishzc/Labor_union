"""Pure LINE identity-review candidate and state rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineReviewRequestId, LineUserId
from domains.line.identity_binding import LineBindingSubjectType
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, ExpectedVersion
from shared_kernel.validation import require_canonical_text

_DECISION_REASON_MAXIMUM_LENGTH = 1_000


class LineReviewType(StrEnum):
    CLIENT_REBIND = "client_rebind"
    STAFF_VERIFICATION = "staff_verification"
    ADMIN_BINDING = "admin_binding"


class LineReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class LineReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class LineReviewStateConflict(ValueError):
    """Raised when a review is stale or no longer decidable."""


@dataclass(frozen=True, slots=True)
class LineReviewSnapshot:
    request_id: LineReviewRequestId
    review_type: LineReviewType
    status: LineReviewStatus
    version: ExpectedVersion
    line_user_id: LineUserId | None = None
    subject_type: LineBindingSubjectType | None = None
    subject_reference: str | None = None
    request_fingerprint: PreviewFingerprint | None = None
    evidence_json: str = "{}"
    assigned_admin_id: int | None = None
    assigned_at: datetime | None = None
    due_at: datetime | None = None
    reassignment_count: int = 0
    reviewed_by_actor_id: str | None = None
    decision_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.review_type, LineReviewType):
            raise TypeError("LINE review type is invalid")
        if not isinstance(self.status, LineReviewStatus):
            raise TypeError("LINE review status is invalid")
        if self.subject_type is not None and not isinstance(
            self.subject_type, LineBindingSubjectType
        ):
            raise TypeError("LINE review subject type is invalid")


@dataclass(frozen=True, slots=True)
class LineReviewDecisionCandidate:
    request_id: LineReviewRequestId
    review_type: LineReviewType
    before_status: LineReviewStatus
    after_status: LineReviewStatus
    expected_version: ExpectedVersion
    resulting_version: ExpectedVersion
    actor: ActorContext
    reason: str
    fingerprint: PreviewFingerprint


# Kept cohesive so the decision transition and fingerprint stay one candidate.
def build_review_decision_candidate(
    snapshot: LineReviewSnapshot,
    decision: LineReviewDecision,
    *,
    expected_version: ExpectedVersion,
    actor: ActorContext,
    reason: str,
) -> LineReviewDecisionCandidate:
    _validate_review_decision(snapshot, decision, expected_version)
    require_canonical_text(reason, "LINE review decision reason", _DECISION_REASON_MAXIMUM_LENGTH)
    return LineReviewDecisionCandidate(
        snapshot.request_id,
        snapshot.review_type,
        snapshot.status,
        _decision_status(decision),
        expected_version,
        ExpectedVersion(expected_version.value + 1),
        actor,
        reason,
        _decision_fingerprint(snapshot, decision, actor, reason),
    )


def _validate_review_decision(
    snapshot: LineReviewSnapshot,
    decision: LineReviewDecision,
    expected_version: ExpectedVersion,
) -> None:
    if not isinstance(decision, LineReviewDecision):
        raise TypeError("LINE review decision is invalid")
    if snapshot.status is not LineReviewStatus.PENDING:
        raise LineReviewStateConflict("LINE review is no longer pending")
    if snapshot.version != expected_version:
        raise LineReviewStateConflict("LINE review candidate is stale")


def _decision_status(decision: LineReviewDecision) -> LineReviewStatus:
    if decision is LineReviewDecision.APPROVE:
        return LineReviewStatus.APPROVED
    return LineReviewStatus.REJECTED


def _decision_fingerprint(
    snapshot: LineReviewSnapshot,
    decision: LineReviewDecision,
    actor: ActorContext,
    reason: str,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "request_id": snapshot.request_id.value,
            "review_type": snapshot.review_type.value,
            "decision": decision.value,
            "expected_version": snapshot.version.value,
            "actor_id": actor.actor_id,
            "reason": reason,
        }
    )


__all__ = [
    "LineReviewDecision",
    "LineReviewDecisionCandidate",
    "LineReviewSnapshot",
    "LineReviewStateConflict",
    "LineReviewStatus",
    "LineReviewType",
    "build_review_decision_candidate",
]

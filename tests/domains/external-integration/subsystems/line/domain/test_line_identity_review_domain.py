"""Module tests for LINE binding and review state rules."""

import pytest

from domains.line.identities import LineReviewRequestId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingConflict,
    LineIdentityBindingStatus,
    LineIdentityClaim,
    transition_binding_status,
)
from domains.line.review import (
    LineReviewDecision,
    LineReviewSnapshot,
    LineReviewStateConflict,
    LineReviewStatus,
    LineReviewType,
    build_review_decision_candidate,
)
from shared_kernel.identities import ActorContext, ExpectedVersion


def _pending_review() -> LineReviewSnapshot:
    return LineReviewSnapshot(
        LineReviewRequestId(10),
        LineReviewType.STAFF_VERIFICATION,
        LineReviewStatus.PENDING,
        ExpectedVersion(2),
    )


def test_identity_claim_keeps_formal_subject_reference() -> None:
    claim = LineIdentityClaim(
        LineUserId("U-staff"),
        LineBindingSubjectType.STAFF,
        "staff:42",
    )

    assert claim.subject_reference == "staff:42"


def test_bound_identity_can_only_move_to_revoked() -> None:
    assert transition_binding_status(
        LineIdentityBindingStatus.BOUND,
        LineIdentityBindingStatus.REVOKED,
    ) is LineIdentityBindingStatus.REVOKED

    with pytest.raises(LineIdentityBindingConflict):
        transition_binding_status(
            LineIdentityBindingStatus.BOUND,
            LineIdentityBindingStatus.PENDING_REVIEW,
        )


def test_review_decision_builds_versioned_candidate() -> None:
    candidate = build_review_decision_candidate(
        _pending_review(),
        LineReviewDecision.APPROVE,
        expected_version=ExpectedVersion(2),
        actor=ActorContext("admin:7", ("line.review.decide",)),
        reason="資料比對一致",
    )

    assert candidate.after_status is LineReviewStatus.APPROVED
    assert candidate.resulting_version == ExpectedVersion(3)
    assert len(candidate.fingerprint.value) == 64


def test_review_decision_rejects_stale_candidate() -> None:
    with pytest.raises(LineReviewStateConflict, match="stale"):
        build_review_decision_candidate(
            _pending_review(),
            LineReviewDecision.REJECT,
            expected_version=ExpectedVersion(1),
            actor=ActorContext("admin:7"),
            reason="資料不符",
        )


def test_completed_review_cannot_be_decided_again() -> None:
    snapshot = LineReviewSnapshot(
        LineReviewRequestId(10),
        LineReviewType.CLIENT_REBIND,
        LineReviewStatus.APPROVED,
        ExpectedVersion(3),
    )

    with pytest.raises(LineReviewStateConflict, match="no longer pending"):
        build_review_decision_candidate(
            snapshot,
            LineReviewDecision.APPROVE,
            expected_version=ExpectedVersion(3),
            actor=ActorContext("admin:7"),
            reason="重複操作",
        )

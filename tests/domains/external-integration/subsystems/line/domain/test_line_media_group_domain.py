"""Module tests for LINE media and order-group policies."""

from datetime import datetime, timezone

import pytest

from domains.line.identities import (
    LineGroupId,
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
)
from domains.line.media import (
    LineMediaCategory,
    LineMediaMetadata,
    LineMediaPolicy,
    LineMediaPolicyViolation,
    validate_media_against_policy,
)
from domains.line.order_group import (
    LineGroupInvitationRelay,
    LineOrderGroupBindingConflict,
    LineOrderGroupBindingSnapshot,
    LineOrderGroupBindingStatus,
    build_order_group_binding_candidate,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion

NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


def _metadata(size_bytes: int = 100) -> LineMediaMetadata:
    return LineMediaMetadata(
        "provider-media-1",
        LineSourceIdentity(
            LineSourceType.USER,
            "U-user",
            LineUserId("U-user"),
        ),
        "image/jpeg",
        size_bytes,
        "a" * 64,
        NOW,
        LineMediaCategory.USER_UPLOAD,
    )


def test_media_policy_accepts_supported_bounded_file() -> None:
    validate_media_against_policy(
        _metadata(),
        LineMediaPolicy(("image/jpeg", "image/png"), 1_000),
    )


def test_media_policy_rejects_oversized_file() -> None:
    with pytest.raises(LineMediaPolicyViolation, match="maximum size"):
        validate_media_against_policy(
            _metadata(2_000),
            LineMediaPolicy(("image/jpeg",), 1_000),
        )


def _bound_group_snapshot() -> LineOrderGroupBindingSnapshot:
    return LineOrderGroupBindingSnapshot(
        "CASE-1",
        LineGroupId("C-group-1"),
        LineOrderGroupBindingStatus.BOUND,
        ExpectedVersion(2),
    )


def test_group_binding_rejects_same_group() -> None:
    with pytest.raises(LineOrderGroupBindingConflict, match="already bound"):
        build_order_group_binding_candidate(
            _bound_group_snapshot(),
            group_id=LineGroupId("C-group-1"),
            expected_version=ExpectedVersion(2),
            actor=ActorContext("admin:1"),
        )


def test_group_binding_rejects_stale_version() -> None:
    with pytest.raises(LineOrderGroupBindingConflict, match="stale"):
        build_order_group_binding_candidate(
            _bound_group_snapshot(),
            group_id=LineGroupId("C-group-2"),
            expected_version=ExpectedVersion(1),
            actor=ActorContext("admin:1"),
        )


def test_invitation_url_is_transient_and_not_in_audit_payload() -> None:
    invitation_url = "https://line.me/R/ti/g/invitation-token"
    relay = LineGroupInvitationRelay(
        "CASE-1",
        LineGroupId("C-group-1"),
        invitation_url,
        (LineUserId("U-customer"), LineUserId("U-staff")),
        ActorContext("admin:1"),
        CorrelationId("correlation:1"),
    )

    audit_payload = relay.persistent_audit_payload()
    assert invitation_url not in repr(relay)
    assert invitation_url not in str(audit_payload)
    assert audit_payload["invitation_fingerprint"] == relay.invitation_fingerprint.value


def test_invitation_rejects_non_line_host() -> None:
    with pytest.raises(ValueError, match="approved LINE host"):
        LineGroupInvitationRelay(
            "CASE-1",
            LineGroupId("C-group-1"),
            "https://example.com/invitation-token",
            (LineUserId("U-customer"),),
            ActorContext("admin:1"),
            CorrelationId("correlation:1"),
        )

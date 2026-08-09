"""Stage 4 domain tests for friend state and one-use LIFF identity flows."""

from datetime import datetime, timedelta, timezone

import pytest

from domains.line.identities import LineIdentityFlowId, LineUserId, LineWebhookEventId
from domains.line.identity_flow import (
    LineIdentityFlowConflict,
    LineIdentityFlowPurpose,
    LineIdentityFlowSnapshot,
    LineIdentityFlowStatus,
    validate_identity_flow,
)
from domains.line.platform_user import (
    LineFriendEvent,
    LineFriendEventType,
    LineFriendStatus,
    friend_status_for_event,
)

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _active_flow() -> LineIdentityFlowSnapshot:
    return LineIdentityFlowSnapshot(
        LineIdentityFlowId("flow-1"),
        LineIdentityFlowPurpose.STAFF_VERIFICATION,
        LineUserId("U-staff"),
        LineIdentityFlowStatus.ACTIVE,
        NOW + timedelta(minutes=15),
        "identity-flow:staff:event-1",
    )


def test_identity_flow_requires_same_user_and_purpose() -> None:
    flow = _active_flow()
    validate_identity_flow(
        flow,
        purpose=LineIdentityFlowPurpose.STAFF_VERIFICATION,
        line_user_id=LineUserId("U-staff"),
        now=NOW,
    )

    with pytest.raises(LineIdentityFlowConflict, match="another user"):
        validate_identity_flow(
            flow,
            purpose=LineIdentityFlowPurpose.STAFF_VERIFICATION,
            line_user_id=LineUserId("U-other"),
            now=NOW,
        )


def test_identity_flow_rejects_expiry_and_replay() -> None:
    expired = LineIdentityFlowSnapshot(
        LineIdentityFlowId("flow-expired"),
        LineIdentityFlowPurpose.CUSTOMER_BINDING,
        LineUserId("U-customer"),
        LineIdentityFlowStatus.ACTIVE,
        NOW,
        "flow-expired",
    )
    with pytest.raises(LineIdentityFlowConflict, match="expired"):
        validate_identity_flow(
            expired,
            purpose=LineIdentityFlowPurpose.CUSTOMER_BINDING,
            line_user_id=LineUserId("U-customer"),
            now=NOW,
        )

    used = LineIdentityFlowSnapshot(
        _active_flow().flow_id,
        _active_flow().purpose,
        _active_flow().line_user_id,
        LineIdentityFlowStatus.USED,
        _active_flow().expires_at,
        _active_flow().idempotency_key,
    )
    with pytest.raises(LineIdentityFlowConflict, match="no longer active"):
        validate_identity_flow(
            used,
            purpose=used.purpose,
            line_user_id=used.line_user_id,
            now=NOW,
        )


def test_message_activity_is_valid_evidence_of_active_friend_state() -> None:
    event = LineFriendEvent(
        LineUserId("U-user"),
        LineWebhookEventId("event-1"),
        LineFriendEventType.ACTIVITY,
        NOW,
    )

    assert event.event_type is LineFriendEventType.ACTIVITY
    assert friend_status_for_event(event.event_type) is LineFriendStatus.ACTIVE

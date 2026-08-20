"""
File: test_line_delivery_domain.py
Description: 驗證 LINE 投遞狀態、lease、重試與刪除規則的安全轉換。
"""

from datetime import datetime, timedelta, timezone

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryAttemptOutcome,
    LineDeliveryLease,
    LineDeliveryRequest,
    LineDeliveryStateConflict,
    LineDeliveryStatus,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
    LineRetryPolicy,
    lease_is_active,
    plan_delivery_attempt,
    transition_delivery_status,
)
from domains.line.identities import LineDeliveryTaskId, LineGroupId, LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey

NOW = datetime(2026, 8, 6, 10, tzinfo=timezone.utc)


def _request() -> LineDeliveryRequest:
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId("U-customer")),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"text": "測試訊息"}),
        NOW,
        IdempotencyKey("delivery:1"),
        CorrelationId("correlation:1"),
        "order",
        "case:1150729",
    )


def test_delivery_request_contains_canonical_payload() -> None:
    request = _request()

    assert request.payload_json == '{"text":"測試訊息"}'
    assert request.fingerprint == _request().fingerprint


def test_recipient_type_must_match_identity() -> None:
    with pytest.raises(TypeError, match="do not match"):
        LineRecipient(LineRecipientType.GROUP, LineUserId("U-user"))


def test_retry_policy_uses_exponential_backoff() -> None:
    policy = LineRetryPolicy(5, 10, 60)
    plan = plan_delivery_attempt(
        policy,
        completed_attempts=3,
        outcome=LineDeliveryAttemptOutcome.RETRYABLE_FAILURE,
        completed_at=NOW,
    )

    assert plan.resulting_status is LineDeliveryStatus.RETRYABLE_FAILED
    assert plan.next_attempt_at == NOW + timedelta(seconds=40)


def test_provider_retry_after_is_respected() -> None:
    plan = plan_delivery_attempt(
        LineRetryPolicy(5, 10, 60),
        completed_attempts=1,
        outcome=LineDeliveryAttemptOutcome.RETRYABLE_FAILURE,
        completed_at=NOW,
        retry_after_seconds=90,
    )

    assert plan.next_attempt_at == NOW + timedelta(seconds=90)


def test_maximum_attempts_becomes_terminal_failure() -> None:
    plan = plan_delivery_attempt(
        LineRetryPolicy(3, 10, 60),
        completed_attempts=3,
        outcome=LineDeliveryAttemptOutcome.RETRYABLE_FAILURE,
        completed_at=NOW,
    )

    assert plan.resulting_status is LineDeliveryStatus.FAILED
    assert plan.next_attempt_at is None


def test_delivery_rejects_direct_pending_to_sent_transition() -> None:
    with pytest.raises(LineDeliveryStateConflict):
        transition_delivery_status(LineDeliveryStatus.PENDING, LineDeliveryStatus.SENT)


def test_processing_delivery_can_be_cancelled_before_provider_send() -> None:
    assert transition_delivery_status(
        LineDeliveryStatus.PROCESSING, LineDeliveryStatus.CANCELLED
    ) is LineDeliveryStatus.CANCELLED


def test_lease_activity_uses_bounded_time_window() -> None:
    lease = LineDeliveryLease(
        LineDeliveryTaskId(5),
        "worker:1",
        NOW,
        NOW + timedelta(minutes=1),
    )

    assert lease_is_active(lease, NOW + timedelta(seconds=30)) is True
    assert lease_is_active(lease, NOW + timedelta(minutes=1)) is False

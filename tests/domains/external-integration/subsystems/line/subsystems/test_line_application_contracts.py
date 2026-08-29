"""Subsystem contract tests for bounded LINE commands and results."""

from datetime import datetime, timezone

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineProviderMessageId, LineUserId
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityClaim
from domains.line.review import LineReviewStatus, LineReviewType
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.capabilities import (
    LineCapability,
    LineCapabilityDeniedError,
    require_line_capability,
)
from subsystems.line.delivery_contracts import (
    ClaimLineDeliveryTasksQuery,
    LineProviderOutcome,
    LineProviderOutcomeType,
    provider_attempt_outcome,
)
from subsystems.line.identity_contracts import BindAdminLineIdentityCommand
from subsystems.line.review_contracts import LineReviewListQuery

NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


def test_admin_binding_command_rejects_staff_claim() -> None:
    with pytest.raises(ValueError, match="admin identity claim"):
        BindAdminLineIdentityCommand(
            LineIdentityClaim(
                LineUserId("U-staff"),
                LineBindingSubjectType.STAFF,
                "staff:1",
            ),
            ExpectedVersion(0),
            ActorContext("admin:1"),
            IdempotencyKey("bind:1"),
            CorrelationId("correlation:1"),
        )


def test_review_query_is_bounded() -> None:
    query = LineReviewListQuery(
        statuses=(LineReviewStatus.PENDING,),
        review_types=(LineReviewType.STAFF_VERIFICATION,),
        page_size=100,
    )
    assert query.page_size == 100

    with pytest.raises(ValueError, match="exceeds maximum"):
        LineReviewListQuery(page_size=101)


def test_delivery_claim_query_is_bounded() -> None:
    with pytest.raises(ValueError, match="exceeds maximum"):
        ClaimLineDeliveryTasksQuery("worker:1", NOW, 101)


def test_provider_outcome_requires_success_identity() -> None:
    with pytest.raises(ValueError, match="provider message ID"):
        LineProviderOutcome(LineProviderOutcomeType.SUCCESS)

    outcome = LineProviderOutcome(
        LineProviderOutcomeType.SUCCESS,
        provider_message_id=LineProviderMessageId("provider-message-1"),
    )
    assert provider_attempt_outcome(outcome).value == "success"


def test_human_capabilities_are_distinct_from_internal_authentication() -> None:
    capability_values = {item.value for item in LineCapability}

    assert "line.review.decide" in capability_values
    assert "line.order_group.bind" in capability_values
    assert all("internal" not in item for item in capability_values)


def test_human_capability_requires_explicit_actor_permission() -> None:
    authorized = ActorContext("admin:1", ("line.review.decide",))
    require_line_capability(authorized, LineCapability.REVIEW_DECIDE)

    with pytest.raises(LineCapabilityDeniedError):
        require_line_capability(authorized, LineCapability.ORDER_GROUP_BIND)


def test_delivery_request_is_framework_neutral() -> None:
    request = LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId("U-user")),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"text": "hello"}),
        NOW,
        IdempotencyKey("delivery:1"),
        CorrelationId("correlation:1"),
        "review",
        "review:1",
    )

    assert request.recipient.identity == LineUserId("U-user")

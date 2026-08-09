"""Stage 7 matching notification command boundaries."""

from datetime import datetime, timezone

import pytest

from domains.line.identities import LineUserId
from domains.scheduling.matching_communication import (
    CaregiverWillingness,
    CustomerMatchingDecision,
    MatchingNotificationKind,
    MatchingPlanReference,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.scheduling.matching_notification_contracts import (
    RecordCaregiverLineResponseCommand,
    RecordManualMatchingResponseCommand,
    RequestCaregiverInformationCommand,
)

NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)
PLAN = MatchingPlanReference("CASE-1", 10, 2)
ACTOR = ActorContext("admin:1", ("line.matching.send",))


def test_caregiver_notification_accepts_only_caregiver_information_kinds() -> None:
    command = RequestCaregiverInformationCommand(
        PLAN,
        20,
        MatchingNotificationKind.CAREGIVER_INFO_1,
        ACTOR,
        ExpectedVersion(2),
        IdempotencyKey("matching-info:1"),
        CorrelationId("correlation:1"),
    )
    assert command.fingerprint == command.fingerprint

    with pytest.raises(ValueError, match="caregiver notification kind"):
        RequestCaregiverInformationCommand(
            PLAN,
            20,
            MatchingNotificationKind.CUSTOMER_PROFILES,
            ACTOR,
            ExpectedVersion(2),
            IdempotencyKey("matching-info:2"),
            CorrelationId("correlation:2"),
        )


def test_line_response_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RecordCaregiverLineResponseCommand(
            "token-1",
            LineUserId("U-caregiver"),
            CaregiverWillingness.WILLING,
            datetime(2026, 8, 9),
            IdempotencyKey("response:1"),
            CorrelationId("correlation:1"),
        )


def test_manual_override_requires_reason_and_exactly_one_decision() -> None:
    command = RecordManualMatchingResponseCommand(
        PLAN,
        20,
        CaregiverWillingness.WILLING,
        None,
        "月嫂以電話確認願意承接",
        ACTOR,
        ExpectedVersion(2),
        IdempotencyKey("manual-response:1"),
        CorrelationId("correlation:1"),
    )
    assert command.segment_id == 20

    with pytest.raises(ValueError, match="exactly one decision"):
        RecordManualMatchingResponseCommand(
            PLAN,
            None,
            None,
            None,
            "人工處理",
            ACTOR,
            ExpectedVersion(2),
            IdempotencyKey("manual-response:2"),
            CorrelationId("correlation:2"),
        )

    with pytest.raises(ValueError, match="exactly one decision"):
        RecordManualMatchingResponseCommand(
            PLAN,
            20,
            CaregiverWillingness.WILLING,
            CustomerMatchingDecision.ACCEPTED,
            "人工處理",
            ACTOR,
            ExpectedVersion(2),
            IdempotencyKey("manual-response:3"),
            CorrelationId("correlation:3"),
        )

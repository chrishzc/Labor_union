"""Typed commands and results for canonical matching notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineDeliveryTaskId, LineUserId
from domains.scheduling.matching_communication import (
    CaregiverWillingness,
    CustomerMatchingDecision,
    MatchingNotificationKind,
    MatchingPlanReference,
    MatchingResponseSource,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.validation import require_canonical_text, require_positive_integer

_REASON_MAXIMUM_LENGTH = 500


class MatchingNotificationProjectionStatus(StrEnum):
    PENDING = "pending"
    PROJECTED = "projected"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class RequestCaregiverInformationCommand:
    plan: MatchingPlanReference
    segment_id: int
    notification_kind: MatchingNotificationKind
    actor: ActorContext
    expected_version: ExpectedVersion
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_positive_integer(self.segment_id, "matching segment ID")
        allowed = {
            MatchingNotificationKind.CAREGIVER_INFO_1,
            MatchingNotificationKind.CAREGIVER_INFO_2,
        }
        if self.notification_kind not in allowed:
            raise ValueError("caregiver notification kind is invalid")

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(_caregiver_information_payload(self))


@dataclass(frozen=True, slots=True)
class RequestCustomerProfilesCommand:
    plan: MatchingPlanReference
    actor: ActorContext
    expected_version: ExpectedVersion
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {"plan_id": self.plan.plan_id, "plan_version": self.plan.version}
        )


@dataclass(frozen=True, slots=True)
class RecordCaregiverLineResponseCommand:
    interaction_token: str
    line_user_id: LineUserId
    willingness: CaregiverWillingness
    occurred_at: datetime
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_response(self.interaction_token, self.occurred_at)


@dataclass(frozen=True, slots=True)
class RecordCustomerLineDecisionCommand:
    interaction_token: str
    line_user_id: LineUserId
    decision: CustomerMatchingDecision
    occurred_at: datetime
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_response(self.interaction_token, self.occurred_at)


@dataclass(frozen=True, slots=True)
class RecordManualMatchingResponseCommand:
    plan: MatchingPlanReference
    segment_id: int | None
    caregiver_willingness: CaregiverWillingness | None
    customer_decision: CustomerMatchingDecision | None
    reason: str
    actor: ActorContext
    expected_version: ExpectedVersion
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "manual matching reason", _REASON_MAXIMUM_LENGTH)
        _validate_manual_response(self)


@dataclass(frozen=True, slots=True)
class MatchingNotificationAudience:
    line_user_id: LineUserId
    display_name: str
    subject_reference: str

    def __post_init__(self) -> None:
        require_canonical_text(self.display_name, "matching audience name", 100)
        require_canonical_text(self.subject_reference, "matching audience reference", 191)


@dataclass(frozen=True, slots=True)
class MatchingNotificationResult:
    intent_id: int
    plan: MatchingPlanReference
    notification_kind: MatchingNotificationKind
    projection_status: MatchingNotificationProjectionStatus
    line_delivery_task_id: LineDeliveryTaskId | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.intent_id, "matching notification intent ID")


@dataclass(frozen=True, slots=True)
class MatchingResponseResult:
    event_id: int
    plan: MatchingPlanReference
    source: MatchingResponseSource
    caregiver_willingness: CaregiverWillingness | None = None
    customer_decision: CustomerMatchingDecision | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.event_id, "matching response event ID")


def _caregiver_information_payload(
    command: RequestCaregiverInformationCommand,
) -> dict[str, int | str]:
    return {
        "plan_id": command.plan.plan_id,
        "plan_version": command.plan.version,
        "segment_id": command.segment_id,
        "notification_kind": command.notification_kind.value,
    }


def _validate_response(interaction_token: str, occurred_at: datetime) -> None:
    require_canonical_text(interaction_token, "matching interaction token", 191)
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("matching response time must be timezone-aware")


def _validate_manual_response(command: RecordManualMatchingResponseCommand) -> None:
    choices = (
        command.caregiver_willingness is not None,
        command.customer_decision is not None,
    )
    if sum(choices) != 1:
        raise ValueError("manual matching response must contain exactly one decision")
    if command.caregiver_willingness is not None and command.segment_id is None:
        raise ValueError("manual caregiver response requires a segment ID")
    if command.customer_decision is not None and command.segment_id is not None:
        raise ValueError("manual customer decision cannot contain a segment ID")


__all__ = [
    "MatchingNotificationAudience",
    "MatchingNotificationProjectionStatus",
    "MatchingNotificationResult",
    "MatchingResponseResult",
    "RecordCaregiverLineResponseCommand",
    "RecordCustomerLineDecisionCommand",
    "RecordManualMatchingResponseCommand",
    "RequestCaregiverInformationCommand",
    "RequestCustomerProfilesCommand",
]

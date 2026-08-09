"""Typed commands and results for canonical matching notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineDeliveryTaskId, LineUserId
from domains.line.delivery import LineDeliveryStatus
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
        _require_matching_version(self.plan, self.expected_version)

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(_caregiver_information_payload(self))


@dataclass(frozen=True, slots=True)
class RequestCustomerProfilesCommand:
    plan: MatchingPlanReference
    note: str
    actor: ActorContext
    expected_version: ExpectedVersion
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.note, "customer profile note", 1000)
        _require_matching_version(self.plan, self.expected_version)

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {
                "plan_id": self.plan.plan_id,
                "plan_version": self.plan.version,
                "note": self.note,
            }
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
        _require_matching_version(self.plan, self.expected_version)
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
class MatchingSegmentContact:
    segment_id: int
    segment_order: int
    staff_id: int
    staff_name: str
    staff_line_user_id: LineUserId | None
    assigned_start_date: str
    assigned_end_date: str
    willingness: CaregiverWillingness
    information_1_status: LineDeliveryStatus | None = None
    information_2_status: LineDeliveryStatus | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.segment_id, "matching segment ID")
        require_positive_integer(self.segment_order, "matching segment order")
        require_positive_integer(self.staff_id, "matching staff ID")
        require_canonical_text(self.staff_name, "matching staff name", 100)


@dataclass(frozen=True, slots=True)
class MatchingContactState:
    plan: MatchingPlanReference
    plan_status: str
    plan_is_active: bool
    order_status: str
    customer_line_user_id: LineUserId | None
    customer_decision: CustomerMatchingDecision
    customer_profiles_status: LineDeliveryStatus | None
    segments: tuple[MatchingSegmentContact, ...]

    @property
    def all_willing(self) -> bool:
        return bool(self.segments) and all(
            segment.willingness is CaregiverWillingness.WILLING
            for segment in self.segments
        )


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


def _require_matching_version(
    plan: MatchingPlanReference,
    expected_version: ExpectedVersion,
) -> None:
    if plan.version != expected_version.value:
        raise ValueError("matching plan and expected versions do not match")


__all__ = [
    "MatchingNotificationAudience",
    "MatchingContactState",
    "MatchingNotificationProjectionStatus",
    "MatchingNotificationResult",
    "MatchingResponseResult",
    "MatchingSegmentContact",
    "RecordCaregiverLineResponseCommand",
    "RecordCustomerLineDecisionCommand",
    "RecordManualMatchingResponseCommand",
    "RequestCaregiverInformationCommand",
    "RequestCustomerProfilesCommand",
]

"""File: matching_notification_contracts.py
Description: 定義 M3 媒合協調與 LINE 互動的 typed contracts。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
from shared_kernel.validation import require_canonical_text, require_positive_half_hour, require_positive_integer

_REASON_MAXIMUM_LENGTH = 500


class MatchingNotificationProjectionStatus(StrEnum):
    PENDING = "pending"
    PROJECTED = "projected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ManualMatchingConfirmationMethod(StrEnum):
    PHONE = "phone"
    IN_PERSON = "in_person"
    PAPER = "paper"
    OTHER = "other"


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
class CustomerConfirmationResumePreview:
    staff_id: int
    staff_name: str
    ready: bool
    filename: str | None = None
    version: int | None = None
    blocker: str | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "matching confirmation staff ID")
        require_canonical_text(self.staff_name, "matching confirmation staff name", 100)
        if self.ready:
            if not self.filename or self.version is None or self.version <= 0 or self.blocker is not None:
                raise ValueError("ready matching confirmation resume preview is incomplete")
        elif not self.blocker:
            raise ValueError("blocked matching confirmation resume preview requires a blocker")


@dataclass(frozen=True, slots=True)
class CustomerConfirmationInformationPreview:
    segment_id: int
    staff_id: int
    staff_name: str
    text: str

    def __post_init__(self) -> None:
        require_positive_integer(self.segment_id, "matching information segment ID")
        require_positive_integer(self.staff_id, "matching information staff ID")
        require_canonical_text(self.staff_name, "matching information staff name", 100)
        require_canonical_text(self.text, "matching information text", 5000)


@dataclass(frozen=True, slots=True)
class CustomerConfirmationWeeklyServicePreview:
    serial_number: int
    staff_name: str
    week_start_date: str
    week_end_date: str
    service_hours_per_day: float | int
    weekly_work_days: int
    weekly_hours: float | int

    def __post_init__(self) -> None:
        require_positive_integer(self.serial_number, "weekly service serial number")
        require_canonical_text(self.staff_name, "weekly service staff name", 100)
        require_canonical_text(self.week_start_date, "weekly service start date", 10)
        require_canonical_text(self.week_end_date, "weekly service end date", 10)
        require_positive_half_hour(self.service_hours_per_day, "weekly service hours per day")
        if self.weekly_work_days < 0 or self.weekly_hours < 0:
            raise ValueError("matching confirmation weekly service values are invalid")


@dataclass(frozen=True, slots=True)
class CustomerConfirmationPreview:
    plan: MatchingPlanReference
    order_information_1_ready: bool
    order_information_2_ready: bool
    weekly_service_ready: bool
    weekly_service_row_count: int
    order_information_1: tuple[CustomerConfirmationInformationPreview, ...]
    order_information_2: tuple[CustomerConfirmationInformationPreview, ...]
    weekly_service_rows: tuple[CustomerConfirmationWeeklyServicePreview, ...]
    caregiver_resumes: tuple[CustomerConfirmationResumePreview, ...]
    blockers: tuple[str, ...]

    @property
    def send_allowed(self) -> bool:
        return not self.blockers

    def __post_init__(self) -> None:
        if self.weekly_service_row_count < 0:
            raise ValueError("matching confirmation weekly row count is invalid")
        if not self.caregiver_resumes:
            raise ValueError("matching confirmation preview requires caregivers")


@dataclass(frozen=True, slots=True)
class PreviewManualCustomerProfilesCommand:
    plan: MatchingPlanReference
    confirmation_method: ManualMatchingConfirmationMethod
    reason: str
    actor: ActorContext
    expected_version: ExpectedVersion

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "manual customer profiles reason", _REASON_MAXIMUM_LENGTH)
        _require_matching_version(self.plan, self.expected_version)

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {
                "case_no": self.plan.case_no,
                "plan_id": self.plan.plan_id,
                "plan_version": self.plan.version,
                "confirmation_method": self.confirmation_method.value,
                "reason": self.reason,
                "actor_id": self.actor.actor_id,
            }
        )


@dataclass(frozen=True, slots=True)
class ApplyManualCustomerProfilesCommand(PreviewManualCustomerProfilesCommand):
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        PreviewManualCustomerProfilesCommand.__post_init__(self)
        if not isinstance(self.preview_fingerprint, PreviewFingerprint):
            raise TypeError("manual customer profiles preview fingerprint is invalid")


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
        if (
            self.caregiver_willingness is not None
            and not isinstance(self.caregiver_willingness, CaregiverWillingness)
        ):
            raise TypeError(
                "manual matching caregiver willingness must be CaregiverWillingness or None"
            )
        if (
            self.customer_decision is not None
            and not isinstance(self.customer_decision, CustomerMatchingDecision)
        ):
            raise TypeError(
                "manual matching customer decision must be CustomerMatchingDecision or None"
            )
        _validate_manual_response(self)


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
    customer_profiles_manual_confirmation: "ManualCustomerProfilesEvidence | None" = None

    @property
    def all_willing(self) -> bool:
        return bool(self.segments) and all(
            segment.willingness is CaregiverWillingness.WILLING
            for segment in self.segments
        )

    @property
    def customer_profiles_are_available(self) -> bool:
        return (
            self.customer_profiles_status is not None
            or self.customer_profiles_manual_confirmation is not None
        )


@dataclass(frozen=True, slots=True)
class ManualCustomerProfilesEvidence:
    event_ids: tuple[int, ...]
    confirmation_method: ManualMatchingConfirmationMethod
    reason: str
    actor_id: str
    idempotency_key: IdempotencyKey
    preview_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        if not self.event_ids or any(event_id <= 0 for event_id in self.event_ids):
            raise ValueError("manual customer profiles event IDs are invalid")
        require_canonical_text(self.reason, "manual customer profiles reason", _REASON_MAXIMUM_LENGTH)
        require_canonical_text(self.actor_id, "manual customer profiles actor", 191)


@dataclass(frozen=True, slots=True)
class ManualCustomerProfilesPreview:
    plan: MatchingPlanReference
    segment_ids: tuple[int, ...]
    confirmation_method: ManualMatchingConfirmationMethod
    reason: str
    preview_fingerprint: PreviewFingerprint
    apply_allowed: bool = True


@dataclass(frozen=True, slots=True)
class ManualCustomerProfilesReceipt:
    plan: MatchingPlanReference
    evidence: ManualCustomerProfilesEvidence
    replayed: bool


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
    segment_id: int | None = None
    idempotency_key: IdempotencyKey | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.event_id, "matching response event ID")
        if self.segment_id is not None:
            require_positive_integer(self.segment_id, "matching response segment ID")
        if self.idempotency_key is not None and not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("matching response idempotency key must be IdempotencyKey or None")


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
    "ApplyManualCustomerProfilesCommand",
    "CustomerConfirmationInformationPreview",
    "CustomerConfirmationPreview",
    "CustomerConfirmationResumePreview",
    "CustomerConfirmationWeeklyServicePreview",
    "ManualCustomerProfilesEvidence",
    "ManualCustomerProfilesPreview",
    "ManualCustomerProfilesReceipt",
    "ManualMatchingConfirmationMethod",
    "MatchingContactState",
    "MatchingNotificationProjectionStatus",
    "MatchingNotificationResult",
    "MatchingResponseResult",
    "MatchingSegmentContact",
    "PreviewManualCustomerProfilesCommand",
    "RecordCaregiverLineResponseCommand",
    "RecordCustomerLineDecisionCommand",
    "RecordManualMatchingResponseCommand",
    "RequestCaregiverInformationCommand",
    "RequestCustomerProfilesCommand",
]

"""File: matching_notification_contracts.py
Description: 定義 M3 assignment conversion 後雙向 LINE intent 的 typed contracts。
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
from domains.scheduling.matching_coordination import (
    MatchingCrossDomainRequest,
    MatchingRequestKind,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.validation import require_canonical_text, require_positive_integer
from subsystems.scheduling.matching_assignment_conversion import (
    AssignmentConversionResultState,
    CanonicalAssignmentConversionReceipt,
)

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
class NotifyAssignmentConversionCommand:
    request: MatchingCrossDomainRequest
    receipt: CanonicalAssignmentConversionReceipt
    customer: MatchingNotificationAudience
    caregiver: MatchingNotificationAudience
    actor: ActorContext
    scheduled_at: datetime
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        typed_values = (
            (self.request, MatchingCrossDomainRequest, "request"),
            (self.receipt, CanonicalAssignmentConversionReceipt, "receipt"),
            (self.customer, MatchingNotificationAudience, "customer"),
            (self.caregiver, MatchingNotificationAudience, "caregiver"),
            (self.actor, ActorContext, "actor"),
            (self.scheduled_at, datetime, "scheduled_at"),
            (self.idempotency_key, IdempotencyKey, "idempotency_key"),
            (self.correlation_id, CorrelationId, "correlation_id"),
        )
        for value, expected_type, field_name in typed_values:
            if not isinstance(value, expected_type):
                raise TypeError(f"assignment conversion notification {field_name} must be {expected_type.__name__}")
        if self.request.request_kind is not MatchingRequestKind.ASSIGNMENT_CONVERSION_REQUESTED:
            raise ValueError("assignment conversion notification request kind is invalid")
        if not self.request.candidate_id:
            raise ValueError("assignment conversion notification request requires a candidate")
        if self.receipt.result_state is not AssignmentConversionResultState.CONVERTED:
            raise ValueError("assignment conversion notification receipt must be converted")
        if (
            self.receipt.request_id != self.request.request_id
            or self.receipt.package_id != self.request.package_id
            or self.receipt.package_version != self.request.package_version
            or self.receipt.criteria_snapshot_id != self.request.criteria_snapshot_id
            or self.receipt.candidate_id != self.request.candidate_id
            or self.receipt.source_versions != self.request.source_versions
        ):
            raise ValueError("assignment conversion notification receipt does not match request")
        if not isinstance(self.customer.line_user_id, LineUserId):
            raise TypeError("assignment conversion customer line_user_id must be LineUserId")
        if not isinstance(self.caregiver.line_user_id, LineUserId):
            raise TypeError("assignment conversion caregiver line_user_id must be LineUserId")
        if self.customer.subject_reference != self.request.case_no:
            raise ValueError("assignment conversion customer subject reference does not match case")
        if self.caregiver.subject_reference != self.request.candidate_id:
            raise ValueError("assignment conversion caregiver subject reference does not match candidate")
        if self.scheduled_at.tzinfo is None or self.scheduled_at.utcoffset() is None:
            raise ValueError("assignment conversion notification time must be timezone-aware")

    @property
    def fingerprint(self) -> PreviewFingerprint:
        request = self.request
        return fingerprint_payload(
            {
                "request": {
                    "request_id": request.request_id,
                    "request_kind": request.request_kind.value,
                    "case_no": request.case_no,
                    "package_id": request.package_id,
                    "package_version": request.package_version,
                    "criteria_snapshot_id": request.criteria_snapshot_id,
                    "candidate_id": request.candidate_id,
                    "source_versions": tuple(item.as_payload() for item in request.source_versions),
                    "lineage_event_id": request.lineage_event_id,
                    "reason": request.reason,
                },
                "receipt": {
                    "fingerprint": self.receipt.receipt_fingerprint.value,
                    "assignment_reference": self.receipt.assignment_reference,
                },
                "customer": {
                    "line_user_id": self.customer.line_user_id.value,
                    "display_name": self.customer.display_name,
                    "subject_reference": self.customer.subject_reference,
                },
                "caregiver": {
                    "line_user_id": self.caregiver.line_user_id.value,
                    "display_name": self.caregiver.display_name,
                    "subject_reference": self.caregiver.subject_reference,
                },
                "actor_id": self.actor.actor_id,
                "scheduled_at": self.scheduled_at.astimezone(timezone.utc).isoformat(),
            }
        )


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
class AssignmentConversionNotificationResult:
    request_id: str
    customer_task_id: LineDeliveryTaskId
    caregiver_task_id: LineDeliveryTaskId
    replayed: bool

    def __post_init__(self) -> None:
        require_canonical_text(self.request_id, "assignment conversion notification request ID", 191)
        if not isinstance(self.customer_task_id, LineDeliveryTaskId):
            raise TypeError("assignment conversion customer task ID must be LineDeliveryTaskId")
        if not isinstance(self.caregiver_task_id, LineDeliveryTaskId):
            raise TypeError("assignment conversion caregiver task ID must be LineDeliveryTaskId")
        if not isinstance(self.replayed, bool):
            raise TypeError("assignment conversion notification replayed must be bool")


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
    "ApplyManualCustomerProfilesCommand",
    "AssignmentConversionNotificationResult",
    "ManualCustomerProfilesEvidence",
    "ManualCustomerProfilesPreview",
    "ManualCustomerProfilesReceipt",
    "ManualMatchingConfirmationMethod",
    "MatchingNotificationAudience",
    "MatchingContactState",
    "MatchingNotificationProjectionStatus",
    "MatchingNotificationResult",
    "MatchingResponseResult",
    "MatchingSegmentContact",
    "NotifyAssignmentConversionCommand",
    "PreviewManualCustomerProfilesCommand",
    "RecordCaregiverLineResponseCommand",
    "RecordCustomerLineDecisionCommand",
    "RecordManualMatchingResponseCommand",
    "RequestCaregiverInformationCommand",
    "RequestCustomerProfilesCommand",
]

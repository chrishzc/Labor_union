"""
File: matching_coordination.py
Description: 定義 Matching Coordination source-version 的 closed API schema。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domains.scheduling.matching_coordination import (
    SOURCE_KINDS,
    MatchingSourceVersion,
    StableRejectionReason,
)


Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class MatchingCoordinationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class MatchingSourceVersionView(MatchingCoordinationSchema):
    source_kind: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=191)
    version: int | str
    fingerprint: Sha256 | str

    @field_validator("source_kind")
    @classmethod
    def _known_source_kind(cls, value: str) -> str:
        if value not in SOURCE_KINDS:
            raise ValueError("unknown matching source kind")
        return value

    @field_validator("fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        if value == "not_consulted":
            return value
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("fingerprint must be lowercase SHA-256")
        return value


class MatchingSourceTupleView(MatchingCoordinationSchema):
    items: tuple[MatchingSourceVersionView, ...]

    @field_validator("items")
    @classmethod
    def _canonical_tuple(cls, value: tuple[MatchingSourceVersionView, ...]) -> tuple[MatchingSourceVersionView, ...]:
        if tuple(item.source_kind for item in value) != SOURCE_KINDS:
            raise ValueError("source tuple must use canonical source order")
        return value


class MatchingCriteriaSnapshotView(MatchingCoordinationSchema):
    snapshot_id: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    criteria_version: int = Field(ge=0)
    criteria: tuple[tuple[str, Any], ...]
    source_versions: tuple[MatchingSourceVersionView, ...]
    fingerprint: Sha256
    created_at: datetime
    superseded_by: str | None = Field(default=None, min_length=1, max_length=191)

    @field_validator("criteria", mode="before")
    @classmethod
    def _criteria_tuple(cls, value: Any) -> tuple[tuple[str, Any], ...]:
        if not isinstance(value, Mapping):
            return value
        return tuple(sorted(value.items()))

    @field_validator("source_versions")
    @classmethod
    def _source_versions_canonical(
        cls, value: tuple[MatchingSourceVersionView, ...]
    ) -> tuple[MatchingSourceVersionView, ...]:
        if tuple(item.source_kind for item in value) != SOURCE_KINDS:
            raise ValueError("source tuple must use canonical source order")
        return value

    @field_validator("fingerprint", mode="before")
    @classmethod
    def _fingerprint_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)


class MatchingCriteriaResultTransportView(MatchingCoordinationSchema):
    code: str = Field(min_length=1, max_length=80)
    status: Literal["matched", "not_matched", "source_not_ready", "not_consulted"]
    source_version: MatchingSourceVersionView
    detail: str = Field(default="", max_length=500)


class MatchingCandidateResultTransportView(MatchingCoordinationSchema):
    candidate_id: str = Field(min_length=1, max_length=191)
    staff_id: int = Field(gt=0)
    eligibility: Literal["eligible", "ineligible", "expired", "stale"]
    criteria_results: tuple[MatchingCriteriaResultTransportView, ...]
    rejection_reasons: tuple[str, ...]
    coverage_evidence: tuple[date, ...]
    willingness: Literal[
        "unconfirmed",
        "pending",
        "willing",
        "unwilling",
        "expired",
        "stale",
        "recontact_previewed",
        "recontact_queued",
        "silent_excluded",
    ]
    notification_lineage: tuple[str, ...]
    staff_name: str = Field(default="", max_length=100)


class MatchingPackageSegmentTransportView(MatchingCoordinationSchema):
    staff_id: int = Field(gt=0)
    service_dates: tuple[date, ...]
    sequence: int = Field(gt=0)

    @model_validator(mode="before")
    @classmethod
    def _from_domain_segment(cls, value: Any) -> Any:
        if isinstance(value, tuple):
            if len(value) != 3:
                raise ValueError("matching package segment must contain exactly three values")
            return {
                "staff_id": value[0],
                "service_dates": value[1],
                "sequence": value[2],
            }
        return value


class MatchingPackageTransportView(MatchingCoordinationSchema):
    package_id: str = Field(min_length=1, max_length=191)
    version: int = Field(ge=0)
    mode: Literal["single", "multi_segment"]
    segments: tuple[MatchingPackageSegmentTransportView, ...]
    required_service_dates: tuple[date, ...]
    candidate_results: tuple[MatchingCandidateResultTransportView, ...]
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    source_versions: MatchingSourceTupleView
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    state: Literal[
        "candidate_pool_open",
        "proposed",
        "awaiting_caregiver_willingness",
        "awaiting_customer_decision",
        "no_candidate",
        "rematch_required",
    ]
    fingerprint: Sha256

    @field_validator("source_versions", mode="before")
    @classmethod
    def _source_versions_view(cls, value: Any) -> Any:
        if isinstance(value, (tuple, list)):
            return {"items": value}
        return value

    @field_validator("fingerprint", mode="before")
    @classmethod
    def _fingerprint_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)


class RefusalHistoryTransportView(MatchingCoordinationSchema):
    refusal_id: str = Field(min_length=1, max_length=191)
    candidate_id: str = Field(min_length=1, max_length=191)
    snapshot_id: str = Field(min_length=1, max_length=191)
    reason_code: Literal[
        "region_mismatch",
        "service_date_conflict",
        "unavailable_period",
        "waiting_lock_conflict",
        "buffer_conflict",
        "staff_retired",
        "preference_not_ready",
        "preference_mismatch",
        "coverage_incomplete",
        "line_binding_missing",
        "willingness_unconfirmed",
        "incumbent_occupied",
        "due_date_outside_window",
        "criteria_source_stale",
        "candidate_expired",
    ]
    affected_criteria: tuple[str, ...]
    originally_willing: bool
    pain_resolved: bool


class DynamicWillingnessLineageTransportView(MatchingCoordinationSchema):
    event_id: str = Field(min_length=1, max_length=191)
    candidate_id: str = Field(min_length=1, max_length=191)
    staff_id: int = Field(gt=0)
    snapshot_id: str = Field(min_length=1, max_length=191)
    source_versions: MatchingSourceTupleView
    previous_state: Literal[
        "unconfirmed",
        "pending",
        "willing",
        "unwilling",
        "expired",
        "stale",
        "recontact_previewed",
        "recontact_queued",
        "silent_excluded",
    ]
    current_state: Literal[
        "unconfirmed",
        "pending",
        "willing",
        "unwilling",
        "expired",
        "stale",
        "recontact_previewed",
        "recontact_queued",
        "silent_excluded",
    ]
    reason_code: str | None = Field(default=None, min_length=1, max_length=191)
    affected_criteria: tuple[str, ...] = Field(min_length=1)

    @field_validator("source_versions", mode="before")
    @classmethod
    def _source_versions_view(cls, value: Any) -> Any:
        if isinstance(value, (tuple, list)):
            return {"items": value}
        return value


class MatchingCoordinationQueryResponse(MatchingCoordinationSchema):
    case_no: str = Field(min_length=1, max_length=50)
    snapshot: MatchingCriteriaSnapshotView
    package: MatchingPackageTransportView | None
    candidates: tuple[MatchingCandidateResultTransportView, ...]
    source_versions: MatchingSourceTupleView
    refusal_history: tuple[RefusalHistoryTransportView, ...]
    willingness_lineage: tuple[DynamicWillingnessLineageTransportView, ...]
    expected_source_versions_match: bool

    @field_validator("source_versions", mode="before")
    @classmethod
    def _source_versions_view(cls, value: Any) -> Any:
        if isinstance(value, (tuple, list)):
            return {"items": value}
        return value


class MatchingCoordinationQueryRequest(MatchingCoordinationSchema):
    expected_source_versions: MatchingSourceTupleView | None = None


class PreviewInitialCriteriaRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView | None = None


class ApplyInitialCriteriaRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    preview_fingerprint: Sha256


class PreviewCriteriaDiffRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    before_snapshot_id: str = Field(min_length=1, max_length=191)
    after_snapshot_id: str = Field(min_length=1, max_length=191)


class RefusalRoutingTransportView(MatchingCoordinationSchema):
    candidate_id: str = Field(min_length=1, max_length=191)
    refusal_id: str = Field(min_length=1, max_length=191)
    group: Literal[
        "group1_original_willing_reconfirm",
        "group2_pain_resolved_reprobe",
        "group3_unrelated_silent_exclude",
    ]
    action: Literal["reconfirm", "reprobe", "silent_exclude"]
    reason_code: Literal[
        "region_mismatch",
        "service_date_conflict",
        "unavailable_period",
        "waiting_lock_conflict",
        "buffer_conflict",
        "staff_retired",
        "preference_not_ready",
        "preference_mismatch",
        "coverage_incomplete",
        "line_binding_missing",
        "willingness_unconfirmed",
        "incumbent_occupied",
        "due_date_outside_window",
        "criteria_source_stale",
        "candidate_expired",
    ]
    source_snapshot_id: str = Field(min_length=1, max_length=191)
    diff_fingerprint: Sha256

    @field_validator("diff_fingerprint", mode="before")
    @classmethod
    def _fingerprint_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)


class CriteriaDiffTransportView(MatchingCoordinationSchema):
    before_snapshot_id: str = Field(min_length=1, max_length=191)
    after_snapshot_id: str = Field(min_length=1, max_length=191)
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]
    affected_candidate_ids: tuple[str, ...]
    affected_recipient_ids: tuple[str, ...]
    resend_eligible: bool
    diff_fingerprint: Sha256
    refusal_routes: tuple[RefusalRoutingTransportView, ...]

    @field_validator("diff_fingerprint", mode="before")
    @classmethod
    def _fingerprint_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)


class PreviewZeroCandidateRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    policy_id: str = Field(min_length=1, max_length=191)
    policy_version: int = Field(ge=0)
    relaxed_criteria: tuple[str, ...] = Field(min_length=1)

    @field_validator("relaxed_criteria")
    @classmethod
    def _criteria_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("relaxed_criteria must be sorted and unique")
        return value


class ZeroCandidateAlternativeTransportView(MatchingCoordinationSchema):
    alternative_id: str = Field(min_length=1, max_length=191)
    policy_id: str = Field(min_length=1, max_length=191)
    policy_version: int = Field(ge=0)
    relaxed_criteria: tuple[str, ...]
    unchanged_hard_criteria: tuple[str, ...]
    candidate_result: MatchingCandidateResultTransportView | None
    risk_warnings: tuple[str, ...]
    deterministic_rank: int = Field(gt=0)
    preview_fingerprint: Sha256

    @field_validator("preview_fingerprint", mode="before")
    @classmethod
    def _fingerprint_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)


class MatchingPackageSegmentSelection(MatchingCoordinationSchema):
    staff_id: int = Field(gt=0)
    service_dates: tuple[date, ...] = Field(min_length=1)
    sequence: int = Field(gt=0)

    @field_validator("service_dates")
    @classmethod
    def _dates_sorted_unique(cls, value: tuple[date, ...]) -> tuple[date, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("service_dates must be sorted and unique")
        return value


class PreviewMatchingPackageRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    required_service_dates: tuple[date, ...] = Field(min_length=1)
    segments: tuple[MatchingPackageSegmentSelection, ...] = Field(
        min_length=1, max_length=4
    )

    @field_validator("required_service_dates")
    @classmethod
    def _dates_sorted_unique(cls, value: tuple[date, ...]) -> tuple[date, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("required_service_dates must be sorted and unique")
        return value


class PreviewLeaveImpactRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    package_id: str = Field(min_length=1, max_length=191)
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    receipt_key: str = Field(min_length=1, max_length=191)
    expected_leave_version: int = Field(gt=0)
    original_staff_id: int = Field(gt=0)


class PreviewServiceDateRematchRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    package_id: str | None = Field(default=None, min_length=1, max_length=191)
    assignment_id: int = Field(gt=0)
    original_staff_id: int = Field(gt=0)
    original_service_dates: tuple[date, ...] = Field(min_length=1)
    shifted_service_dates: tuple[date, ...] = Field(min_length=1)

    @field_validator("original_service_dates", "shifted_service_dates")
    @classmethod
    def _canonical_service_dates(cls, value: tuple[date, ...]) -> tuple[date, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("service dates must be sorted and unique")
        return value

    @model_validator(mode="after")
    def _requires_a_real_shift(self) -> "PreviewServiceDateRematchRequest":
        if self.original_service_dates == self.shifted_service_dates:
            raise ValueError("shifted service dates must differ from original dates")
        return self


class LeaveImpactPreviewResponse(MatchingCoordinationSchema):
    receipt_key: str = Field(min_length=1, max_length=191)
    result_state: Literal["leave_deferred", "leave_substituted"]
    package_id: str = Field(min_length=1, max_length=191)
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    rematch_required: bool
    resolution_type: Literal["defer_following_assignments", "substitute"]
    original_work_date: date
    resulting_work_date: date
    outcome_event_ids: tuple[str, ...]
    source_versions: MatchingSourceTupleView
    receipt_fingerprint: Sha256
    preview_fingerprint: Sha256
    substitute_staff_id: int | None = Field(default=None, gt=0)

    @field_validator("source_versions", mode="before")
    @classmethod
    def _source_versions_view(cls, value: Any) -> Any:
        if isinstance(value, (tuple, list)):
            return {"items": value}
        return value

    @field_validator("receipt_fingerprint", "preview_fingerprint", mode="before")
    @classmethod
    def _fingerprint_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)


class ServiceDateShiftAvailabilityConfirmationTransportView(MatchingCoordinationSchema):
    intent_id: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    assignment_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    original_service_dates: tuple[date, ...] = Field(min_length=1)
    shifted_service_dates: tuple[date, ...] = Field(min_length=1)
    source_fingerprint: Sha256

    @field_validator("original_service_dates", "shifted_service_dates")
    @classmethod
    def _dates_sorted_unique(cls, value: tuple[date, ...]) -> tuple[date, ...]:
        if any(type(item) is not date for item in value):
            raise ValueError("service dates must be calendar dates")
        if value != tuple(sorted(set(value))):
            raise ValueError("service dates must be sorted and unique")
        return value

    @field_validator("source_fingerprint", mode="before")
    @classmethod
    def _fingerprint_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)


class ServiceDateShiftReassignmentReferenceTransportView(MatchingCoordinationSchema):
    queue_reference: str = Field(min_length=1, max_length=500)
    case_no: str = Field(min_length=1, max_length=50)
    assignment_id: int = Field(gt=0)
    staff_id: int = Field(gt=0)
    shifted_service_dates: tuple[date, ...] = Field(min_length=1)
    conflict_source_ids: tuple[str, ...] = Field(min_length=1)
    source_fingerprint: Sha256

    @field_validator("shifted_service_dates")
    @classmethod
    def _dates_sorted_unique(cls, value: tuple[date, ...]) -> tuple[date, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("shifted service dates must be sorted and unique")
        return value

    @field_validator("conflict_source_ids")
    @classmethod
    def _conflicts_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))) or any(not item.strip() for item in value):
            raise ValueError("conflict sources must be canonical")
        return value

    @field_validator("source_fingerprint", mode="before")
    @classmethod
    def _fingerprint_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)


class ServiceDateRematchPreviewResponse(MatchingCoordinationSchema):
    outcome_kind: Literal["availability_confirmation", "reassignment_reference"]
    availability_confirmation: ServiceDateShiftAvailabilityConfirmationTransportView | None = None
    reassignment_reference: ServiceDateShiftReassignmentReferenceTransportView | None = None

    @model_validator(mode="after")
    def _exactly_one_outcome(self) -> "ServiceDateRematchPreviewResponse":
        expected_confirmation = self.outcome_kind == "availability_confirmation"
        if expected_confirmation != (self.availability_confirmation is not None):
            raise ValueError("service-date outcome does not match confirmation payload")
        if expected_confirmation == (self.reassignment_reference is not None):
            raise ValueError("service-date preview requires exactly one outcome")
        return self


class PreviewRematchRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    package_id: str | None = Field(default=None, min_length=1, max_length=191)


class ApplyCriteriaDiffRequest(PreviewCriteriaDiffRequest):
    preview_fingerprint: Sha256
    recipient_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("recipient_ids")
    @classmethod
    def _recipient_ids_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))) or any(not item.strip() for item in value):
            raise ValueError("recipient IDs must be sorted and unique")
        return value


class ApplyZeroCandidateRequest(PreviewZeroCandidateRequest):
    alternative_id: str = Field(min_length=1, max_length=191)
    preview_fingerprint: Sha256
    decision: Literal["agree", "disagree"]


class PreviewZeroCandidateConfirmationRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    evidence: tuple[str, ...] = Field(min_length=1)
    expected_source_versions: MatchingSourceTupleView
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    package_id: str = Field(min_length=1, max_length=191)
    package_version: int = Field(ge=0)

    @field_validator("evidence")
    @classmethod
    def _evidence_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))) or any(not item.strip() for item in value):
            raise ValueError("evidence must be sorted, unique, and non-empty")
        return value


class ApplyZeroCandidateConfirmationRequest(PreviewZeroCandidateConfirmationRequest):
    preview_fingerprint: Sha256


class ApplyCaregiverSelectionRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    package_id: str = Field(min_length=1, max_length=191)
    package_version: int = Field(ge=0)
    candidate_id: str = Field(min_length=1, max_length=191)
    willingness: Literal["willing", "unwilling"]
    reason_code: str | None = Field(default=None, min_length=1, max_length=191)
    affected_criteria: tuple[str, ...] = ()
    preview_fingerprint: Sha256

    @model_validator(mode="after")
    def _closed_willingness_evidence(self) -> "ApplyCaregiverSelectionRequest":
        if self.willingness == "willing":
            if self.reason_code is not None or self.affected_criteria:
                raise ValueError("willing selection cannot carry refusal evidence")
            return self
        if self.reason_code not in {item.value for item in StableRejectionReason}:
            raise ValueError("unwilling selection requires stable reason code")
        if (
            not self.affected_criteria
            or self.affected_criteria != tuple(sorted(set(self.affected_criteria)))
        ):
            raise ValueError("affected criteria must be sorted, unique, and non-empty")
        return self


class ApplyCustomerDecisionRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    package_id: str = Field(min_length=1, max_length=191)
    package_version: int = Field(ge=0)
    candidate_id: str | None = Field(default=None, min_length=1, max_length=191)
    decision: Literal["accepted", "rejected", "disagree"]
    preview_fingerprint: Sha256


class ApplyRematchRequest(PreviewRematchRequest):
    preview_fingerprint: Sha256


class ApplyLeaveImpactRequest(MatchingCoordinationSchema):
    reason: str = Field(min_length=1, max_length=500)
    expected_source_versions: MatchingSourceTupleView
    package_id: str = Field(min_length=1, max_length=191)
    leave_reference: str = Field(min_length=1, max_length=191)
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    expected_leave_version: int = Field(gt=0)
    original_staff_id: int = Field(gt=0)
    preview_fingerprint: Sha256


class ApplyServiceDateRematchRequest(PreviewServiceDateRematchRequest):
    preview_fingerprint: Sha256


class MatchingCrossDomainRequestTransportView(MatchingCoordinationSchema):
    request_id: str = Field(min_length=1, max_length=191)
    request_kind: Literal["assignment_conversion_requested", "rematch_requested"]
    case_no: str = Field(min_length=1, max_length=50)
    package_id: str = Field(min_length=1, max_length=191)
    package_version: int = Field(ge=0)
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    candidate_id: str | None = Field(default=None, min_length=1, max_length=191)
    source_versions: MatchingSourceTupleView
    lineage_event_id: str = Field(min_length=1, max_length=191)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("source_versions", mode="before")
    @classmethod
    def _source_versions_view(cls, value: Any) -> Any:
        if isinstance(value, (tuple, list)):
            return {"items": value}
        return value


class ZeroCandidateDecisionLineageTransportView(MatchingCoordinationSchema):
    event_id: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    alternative_id: str = Field(min_length=1, max_length=191)
    policy_id: str = Field(min_length=1, max_length=191)
    policy_version: int = Field(ge=0)
    decision: Literal["agree", "disagree"]
    outcome_state: Literal["alternative_agreed_pending_owning_workflows", "awaiting_matching"]
    actor_id: str = Field(min_length=1, max_length=191)
    source_versions: MatchingSourceTupleView
    assignment_request_id: str | None = Field(default=None, min_length=1, max_length=191)

    @field_validator("source_versions", mode="before")
    @classmethod
    def _source_versions_view(cls, value: Any) -> Any:
        if isinstance(value, (tuple, list)):
            return {"items": value}
        return value


class MatchingNotificationIntentTransportView(MatchingCoordinationSchema):
    intent_id: str = Field(min_length=1, max_length=191)
    recipient_role: Literal["customer", "caregiver"]
    recipient_subject_reference: str = Field(min_length=1, max_length=191)
    source_decision_event_id: str = Field(min_length=1, max_length=191)
    criteria_snapshot_id: str = Field(min_length=1, max_length=191)
    package_id: str = Field(min_length=1, max_length=191)
    package_version: int = Field(ge=0)
    package_fingerprint: Sha256
    candidate_id: str = Field(min_length=1, max_length=191)
    idempotency_key: str = Field(min_length=1, max_length=191)
    source_identity: str | None = Field(default=None, min_length=1, max_length=191)
    recipient_selector: str | None = Field(default=None, min_length=1, max_length=191)

    @field_validator("package_fingerprint", "idempotency_key", mode="before")
    @classmethod
    def _wrapped_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)


class MatchingCriteriaRecontactIntentTransportView(MatchingCoordinationSchema):
    intent_id: str = Field(min_length=1, max_length=191)
    recipient_subject_reference: str = Field(min_length=1, max_length=191)
    candidate_id: str = Field(min_length=1, max_length=191)
    staff_id: int = Field(gt=0)
    route_group: Literal[
        "group1_original_willing_reconfirm",
        "group2_pain_resolved_reprobe",
    ]
    action: Literal["reconfirm", "reprobe"]
    reason_code: StableRejectionReason
    before_snapshot_id: str = Field(min_length=1, max_length=191)
    after_snapshot_id: str = Field(min_length=1, max_length=191)
    diff_fingerprint: Sha256
    source_versions: MatchingSourceTupleView
    idempotency_key: str = Field(min_length=1, max_length=191)
    package_id: str | None = Field(default=None, min_length=1, max_length=191)
    package_version: int | None = Field(default=None, ge=0)
    package_fingerprint: Sha256 | None = None

    @field_validator("diff_fingerprint", "package_fingerprint", "idempotency_key", mode="before")
    @classmethod
    def _wrapped_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)

    @field_validator("source_versions", mode="before")
    @classmethod
    def _source_versions_view(cls, value: Any) -> Any:
        if isinstance(value, (tuple, list)):
            return {"items": value}
        return value

    @model_validator(mode="after")
    def _closed_route_and_package_lineage(self) -> "MatchingCriteriaRecontactIntentTransportView":
        expected_action = {
            "group1_original_willing_reconfirm": "reconfirm",
            "group2_pain_resolved_reprobe": "reprobe",
        }[self.route_group]
        if self.action != expected_action:
            raise ValueError("recontact action must match route group")
        package_values = (
            self.package_id,
            self.package_version,
            self.package_fingerprint,
        )
        if any(value is not None for value in package_values) and any(
            value is None for value in package_values
        ):
            raise ValueError("recontact package lineage must be complete")
        return self


class MatchingApplyReceiptResponse(MatchingCoordinationSchema):
    receipt_id: str = Field(min_length=1, max_length=191)
    command_name: Literal[
        "ApplyInitialCriteriaSnapshot",
        "ApplyCriteriaDiffResend",
        "ApplyZeroCandidateAlternative",
        "ApplyZeroCandidateConfirmation",
        "ApplyCaregiverSelection",
        "ApplyCustomerMatchingDecision",
        "ApplyRematch",
        "ApplyLeaveImpactOnMatching",
        "ApplyServiceDateChangeRematch",
    ]
    command_fingerprint: Sha256
    preview_fingerprint: Sha256
    source_versions: MatchingSourceTupleView
    decision_event_id: str | None = Field(default=None, min_length=1, max_length=191)
    package_id: str | None = Field(default=None, min_length=1, max_length=191)
    outbox_intent_ids: tuple[str, ...]
    result_state: Literal[
        "criteria_snapshotted",
        "accepted",
        "rejected",
        "disagree",
        "rematch_required",
        "unconfirmed",
        "pending",
        "willing",
        "unwilling",
        "expired",
        "intent_queued",
        "alternative_agreed_pending_owning_workflows",
        "awaiting_matching",
        "zero_candidate_confirmed",
    ]
    cross_domain_request: MatchingCrossDomainRequestTransportView | None = None
    zero_candidate_decision: ZeroCandidateDecisionLineageTransportView | None = None
    willingness_lineage: DynamicWillingnessLineageTransportView | None = None
    notification_intents: tuple[MatchingNotificationIntentTransportView, ...] = ()
    criteria_recontact_intents: tuple[
        MatchingCriteriaRecontactIntentTransportView, ...
    ] = ()
    resulting_package: MatchingPackageTransportView | None = None

    @field_validator("command_fingerprint", "preview_fingerprint", mode="before")
    @classmethod
    def _fingerprint_value(cls, value: Any) -> Any:
        return getattr(value, "value", value)

    @field_validator("source_versions", mode="before")
    @classmethod
    def _source_versions_view(cls, value: Any) -> Any:
        if isinstance(value, (tuple, list)):
            return {"items": value}
        return value


__all__ = [
    "ApplyZeroCandidateConfirmationRequest",
    "MatchingCoordinationSchema",
    "MatchingCandidateResultTransportView",
    "MatchingCriteriaResultTransportView",
    "MatchingCriteriaSnapshotView",
    "MatchingPackageSegmentTransportView",
    "MatchingPackageTransportView",
    "RefusalHistoryTransportView",
    "DynamicWillingnessLineageTransportView",
    "MatchingCoordinationQueryResponse",
    "PreviewInitialCriteriaRequest",
    "ApplyInitialCriteriaRequest",
    "PreviewCriteriaDiffRequest",
    "RefusalRoutingTransportView",
    "CriteriaDiffTransportView",
    "PreviewZeroCandidateRequest",
    "PreviewZeroCandidateConfirmationRequest",
    "ZeroCandidateAlternativeTransportView",
    "PreviewMatchingPackageRequest",
    "PreviewLeaveImpactRequest",
    "LeaveImpactPreviewResponse",
    "ServiceDateShiftAvailabilityConfirmationTransportView",
    "ServiceDateShiftReassignmentReferenceTransportView",
    "ServiceDateRematchPreviewResponse",
    "PreviewRematchRequest",
    "ApplyCriteriaDiffRequest",
    "ApplyZeroCandidateRequest",
    "ApplyCaregiverSelectionRequest",
    "ApplyCustomerDecisionRequest",
    "ApplyRematchRequest",
    "ApplyLeaveImpactRequest",
    "ApplyServiceDateRematchRequest",
    "MatchingCrossDomainRequestTransportView",
    "ZeroCandidateDecisionLineageTransportView",
    "MatchingNotificationIntentTransportView",
    "MatchingCriteriaRecontactIntentTransportView",
    "MatchingApplyReceiptResponse",
    "PreviewServiceDateRematchRequest",
    "MatchingSourceTupleView",
    "MatchingSourceVersionView",
]

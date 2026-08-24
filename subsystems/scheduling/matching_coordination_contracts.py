"""
File: matching_coordination_contracts.py
Description: 定義 M3 Matching Coordination 的 typed commands、views 與錯誤契約。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass, dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    CriterionStatus,
    MatchingCandidateResult,
    MatchingCriteriaDiff,
    MatchingCriteriaSnapshot,
    DynamicWillingnessLineage,
    MatchingDecisionLineage,
    MatchingCrossDomainRequest,
    MatchingPackage,
    MatchingPackageMode,
    MatchingPackageState,
    MatchingSegment,
    MatchingSourceTuple,
    MatchingSourceVersion,
    RefusalRouting,
    RefusalRoutingGroup,
    ZeroCandidateDecisionLineage,
    ZeroCandidateAlternative,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


class MatchingCommandName(StrEnum):
    QUERY = "QueryMatchingCoordination"
    PREVIEW_INITIAL_CRITERIA = "PreviewInitialCriteriaSnapshot"
    APPLY_INITIAL_CRITERIA = "ApplyInitialCriteriaSnapshot"
    PREVIEW_PACKAGE = "PreviewMatchingPackage"
    PREVIEW_CRITERIA_DIFF_RESEND = "PreviewCriteriaDiffResend"
    APPLY_CRITERIA_DIFF_RESEND = "ApplyCriteriaDiffResend"
    PREVIEW_ZERO_CANDIDATE_ALTERNATIVE = "PreviewZeroCandidateAlternative"
    APPLY_ZERO_CANDIDATE_ALTERNATIVE = "ApplyZeroCandidateAlternative"
    APPLY_CAREGIVER_SELECTION = "ApplyCaregiverSelection"
    APPLY_CUSTOMER_DECISION = "ApplyCustomerMatchingDecision"
    PREVIEW_REMATCH = "PreviewRematch"
    APPLY_REMATCH = "ApplyRematch"
    PREVIEW_LEAVE_IMPACT = "PreviewLeaveImpactOnMatching"
    APPLY_LEAVE_IMPACT = "ApplyLeaveImpactOnMatching"
    PREVIEW_SERVICE_DATE_REMATCH = "PreviewServiceDateChangeRematch"
    APPLY_SERVICE_DATE_REMATCH = "ApplyServiceDateChangeRematch"


MATCHING_ERROR_CODES: tuple[str, ...] = (
    "matching_case_not_found",
    "matching_criteria_invalid",
    "matching_criteria_source_stale",
    "matching_criteria_diff_required",
    "matching_package_not_found",
    "matching_package_stale",
    "matching_source_version_conflict",
    "matching_candidate_not_found",
    "matching_coverage_incomplete",
    "matching_service_date_conflict",
    "matching_unavailability_conflict",
    "matching_staff_retired",
    "matching_preference_source_not_ready",
    "matching_preference_mismatch",
    "matching_willingness_pending",
    "matching_willingness_conflict",
    "matching_rejection_reason_required",
    "matching_recontact_source_stale",
    "matching_no_candidate",
    "matching_alternative_not_explicit",
    "matching_alternative_stale",
    "matching_customer_decision_conflict",
    "matching_customer_acceptance_not_conversion",
    "matching_incumbent_unavailable",
    "matching_rematch_required",
    "matching_leave_reference_stale",
    "matching_leave_resolution_not_applied",
    "matching_assignment_conversion_pending",
    "matching_assignment_conversion_mismatch",
    "matching_idempotency_conflict",
    "matching_invalid_replay_snapshot",
    "matching_lock_set_stale",
    "matching_transaction_failed",
)


class MatchingErrorCode(StrEnum):
    CASE_NOT_FOUND = "matching_case_not_found"
    CRITERIA_INVALID = "matching_criteria_invalid"
    CRITERIA_SOURCE_STALE = "matching_criteria_source_stale"
    CRITERIA_DIFF_REQUIRED = "matching_criteria_diff_required"
    PACKAGE_NOT_FOUND = "matching_package_not_found"
    PACKAGE_STALE = "matching_package_stale"
    SOURCE_VERSION_CONFLICT = "matching_source_version_conflict"
    CANDIDATE_NOT_FOUND = "matching_candidate_not_found"
    COVERAGE_INCOMPLETE = "matching_coverage_incomplete"
    SERVICE_DATE_CONFLICT = "matching_service_date_conflict"
    UNAVAILABILITY_CONFLICT = "matching_unavailability_conflict"
    STAFF_RETIRED = "matching_staff_retired"
    PREFERENCE_SOURCE_NOT_READY = "matching_preference_source_not_ready"
    PREFERENCE_MISMATCH = "matching_preference_mismatch"
    WILLINGNESS_PENDING = "matching_willingness_pending"
    WILLINGNESS_CONFLICT = "matching_willingness_conflict"
    REJECTION_REASON_REQUIRED = "matching_rejection_reason_required"
    RECONTACT_SOURCE_STALE = "matching_recontact_source_stale"
    NO_CANDIDATE = "matching_no_candidate"
    ALTERNATIVE_NOT_EXPLICIT = "matching_alternative_not_explicit"
    ALTERNATIVE_STALE = "matching_alternative_stale"
    CUSTOMER_DECISION_CONFLICT = "matching_customer_decision_conflict"
    CUSTOMER_ACCEPTANCE_NOT_CONVERSION = "matching_customer_acceptance_not_conversion"
    INCUMBENT_UNAVAILABLE = "matching_incumbent_unavailable"
    REMATCH_REQUIRED = "matching_rematch_required"
    LEAVE_REFERENCE_STALE = "matching_leave_reference_stale"
    LEAVE_RESOLUTION_NOT_APPLIED = "matching_leave_resolution_not_applied"
    ASSIGNMENT_CONVERSION_PENDING = "matching_assignment_conversion_pending"
    ASSIGNMENT_CONVERSION_MISMATCH = "matching_assignment_conversion_mismatch"
    IDEMPOTENCY_CONFLICT = "matching_idempotency_conflict"
    INVALID_REPLAY_SNAPSHOT = "matching_invalid_replay_snapshot"
    LOCK_SET_STALE = "matching_lock_set_stale"
    TRANSACTION_FAILED = "matching_transaction_failed"


@dataclass(frozen=True, slots=True)
class MatchingCommand:
    case_no: str
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey
    expected_source_versions: MatchingSourceTuple | None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.reason, "matching command reason", 500)
        if not isinstance(self.actor, ActorContext):
            raise TypeError("matching command actor must be ActorContext")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("matching command correlation_id must be CorrelationId")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("matching command idempotency_key must be IdempotencyKey")
        if self.expected_source_versions is None:
            if isinstance(self, PreviewInitialCriteriaSnapshot):
                return
            raise TypeError("matching source versions are required")
        _validate_sources(self.expected_source_versions)

    @property
    def command_name(self) -> MatchingCommandName:
        return MatchingCommandName(type(self).__name__)


@dataclass(frozen=True, slots=True)
class QueryMatchingCoordination:
    """Read-only command; mutation-only reason/idempotency are absent."""

    case_no: str
    actor: ActorContext
    correlation_id: CorrelationId
    expected_source_versions: MatchingSourceTuple | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if not isinstance(self.actor, ActorContext):
            raise TypeError("matching query actor must be ActorContext")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("matching query correlation_id must be CorrelationId")
        if self.expected_source_versions is not None:
            _validate_sources(self.expected_source_versions)

    @property
    def command_name(self) -> MatchingCommandName:
        return MatchingCommandName.QUERY


@dataclass(frozen=True, slots=True)
class PreviewInitialCriteriaSnapshot(MatchingCommand):
    """Preview the first immutable criteria projection from owner facts."""

    # No prior client-side tuple exists before the first snapshot. The
    # application fresh-reads its source tuple while producing this preview.
    expected_source_versions: MatchingSourceTuple | None


@dataclass(frozen=True, slots=True)
class ApplyInitialCriteriaSnapshot(MatchingCommand):
    """Persist the previewed first criteria snapshot without owner-root writes."""

    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class PreviewMatchingPackage(MatchingCommand):
    criteria_snapshot_id: str
    required_service_dates: tuple[date, ...]
    segments: tuple[MatchingSegment, ...] = ()


@dataclass(frozen=True, slots=True)
class PreviewCriteriaDiffResend(MatchingCommand):
    before_snapshot_id: str
    after_snapshot_id: str


@dataclass(frozen=True, slots=True)
class ApplyCriteriaDiffResend(MatchingCommand):
    before_snapshot_id: str
    after_snapshot_id: str
    preview_fingerprint: PreviewFingerprint
    recipient_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreviewZeroCandidateAlternative(MatchingCommand):
    criteria_snapshot_id: str
    policy_id: str
    policy_version: int
    relaxed_criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.relaxed_criteria:
            return
        if self.relaxed_criteria != tuple(sorted(set(self.relaxed_criteria))):
            raise ValueError("relaxed criteria must be sorted and unique")
        for criterion in self.relaxed_criteria:
            require_canonical_text(criterion, "relaxed criterion", 80)


@dataclass(frozen=True, slots=True)
class ApplyZeroCandidateAlternative(MatchingCommand):
    criteria_snapshot_id: str
    alternative_id: str
    policy_id: str
    policy_version: int
    relaxed_criteria: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint
    decision: str = "agree"

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.relaxed_criteria:
            raise ValueError("relaxed criteria are required")
        if self.relaxed_criteria != tuple(sorted(set(self.relaxed_criteria))):
            raise ValueError("relaxed criteria must be sorted and unique")
        for criterion in self.relaxed_criteria:
            require_canonical_text(criterion, "relaxed criterion", 80)


@dataclass(frozen=True, slots=True)
class ApplyCaregiverSelection(MatchingCommand):
    criteria_snapshot_id: str
    package_id: str
    package_version: int
    candidate_id: str
    willingness: str
    reason_code: str | None
    affected_criteria: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ApplyCustomerMatchingDecision(MatchingCommand):
    criteria_snapshot_id: str
    package_id: str
    package_version: int
    candidate_id: str | None
    decision: str
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class PreviewRematch(MatchingCommand):
    criteria_snapshot_id: str
    package_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApplyRematch(MatchingCommand):
    criteria_snapshot_id: str
    package_id: str | None
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class PreviewLeaveImpactOnMatching(MatchingCommand):
    package_id: str
    leave_reference: str


@dataclass(frozen=True, slots=True)
class ApplyLeaveImpactOnMatching(MatchingCommand):
    package_id: str
    leave_reference: str
    criteria_snapshot_id: str
    expected_leave_version: int
    original_staff_id: int
    preview_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        super().__post_init__()
        require_canonical_text(self.package_id, "package ID", 191)
        require_canonical_text(self.leave_reference, "leave reference", 191)
        require_canonical_text(
            self.criteria_snapshot_id, "criteria snapshot ID", 191
        )
        if self.expected_leave_version <= 0:
            raise ValueError("expected_leave_version must be positive")
        if self.original_staff_id <= 0:
            raise ValueError("original_staff_id must be positive")


@dataclass(frozen=True, slots=True)
class PreviewServiceDateChangeRematch(MatchingCommand):
    criteria_snapshot_id: str
    assignment_id: int
    original_staff_id: int
    original_service_dates: tuple[date, ...]
    shifted_service_dates: tuple[date, ...]
    package_id: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_service_date_change(self)


@dataclass(frozen=True, slots=True)
class ApplyServiceDateChangeRematch(MatchingCommand):
    criteria_snapshot_id: str
    package_id: str | None
    assignment_id: int
    original_staff_id: int
    original_service_dates: tuple[date, ...]
    shifted_service_dates: tuple[date, ...]
    preview_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_service_date_change(self)


def _validate_service_date_change(command: object) -> None:
    require_canonical_text(
        getattr(command, "criteria_snapshot_id"), "criteria snapshot id", 191
    )
    if getattr(command, "assignment_id") <= 0:
        raise ValueError("assignment_id must be positive")
    if getattr(command, "original_staff_id") <= 0:
        raise ValueError("original_staff_id must be positive")
    original = getattr(command, "original_service_dates")
    shifted = getattr(command, "shifted_service_dates")
    for label, values in (
        ("original_service_dates", original),
        ("shifted_service_dates", shifted),
    ):
        if (
            not isinstance(values, tuple)
            or not values
            or any(type(value) is not date for value in values)
            or values != tuple(sorted(set(values)))
        ):
            raise ValueError(f"{label} must be non-empty, sorted, and unique")
    if original == shifted:
        raise ValueError("shifted_service_dates must differ from original dates")


@dataclass(frozen=True, slots=True)
class MatchingCriteriaSnapshotView:
    snapshot_id: str
    case_no: str
    criteria_version: int
    criteria: tuple[tuple[str, Any], ...]
    source_versions: MatchingSourceTuple
    fingerprint: PreviewFingerprint
    created_at: datetime
    superseded_by: str | None


@dataclass(frozen=True, slots=True)
class MatchingCandidateResultView:
    candidate_id: str
    staff_id: int
    eligibility: CandidateEligibility
    criteria_results: tuple[MatchingCriteriaResultView, ...]
    rejection_reasons: tuple[str, ...]
    coverage_evidence: tuple[date, ...]
    willingness: str
    notification_lineage: tuple[str, ...]
    staff_name: str = ""


@dataclass(frozen=True, slots=True)
class MatchingCriteriaResultView:
    code: str
    status: CriterionStatus
    source_version: MatchingSourceVersion
    detail: str


@dataclass(frozen=True, slots=True)
class MatchingPackageView:
    package_id: str
    version: int
    mode: MatchingPackageMode
    segments: tuple[tuple[int, tuple[date, ...], int], ...]
    required_service_dates: tuple[date, ...]
    candidate_results: tuple[MatchingCandidateResultView, ...]
    criteria_snapshot_id: str
    source_versions: MatchingSourceTuple
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    state: MatchingPackageState
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class CriteriaDiffView:
    before_snapshot_id: str
    after_snapshot_id: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]
    affected_candidate_ids: tuple[str, ...]
    affected_recipient_ids: tuple[str, ...]
    resend_eligible: bool
    diff_fingerprint: PreviewFingerprint
    refusal_routes: tuple[RefusalRouting, ...] = ()


class MatchingNotificationRecipientRole(StrEnum):
    CUSTOMER = "customer"
    CAREGIVER = "caregiver"


@dataclass(frozen=True, slots=True)
class MatchingNotificationIntentProjection:
    """Immutable bilateral notification intent; it carries no provider side effect."""

    intent_id: str
    recipient_role: MatchingNotificationRecipientRole
    recipient_subject_reference: str
    source_decision_event_id: str
    criteria_snapshot_id: str
    package_id: str
    package_version: int
    package_fingerprint: PreviewFingerprint
    candidate_id: str
    idempotency_key: IdempotencyKey

    def __post_init__(self) -> None:
        for value, name in (
            (self.intent_id, "matching notification intent ID"),
            (self.recipient_subject_reference, "notification recipient subject reference"),
            (self.source_decision_event_id, "notification source decision event ID"),
            (self.criteria_snapshot_id, "notification criteria snapshot ID"),
            (self.package_id, "notification package ID"),
            (self.candidate_id, "notification candidate ID"),
        ):
            require_canonical_text(value, name, 191)
        if not isinstance(self.recipient_role, MatchingNotificationRecipientRole):
            object.__setattr__(self, "recipient_role", MatchingNotificationRecipientRole(self.recipient_role))
        require_nonnegative_integer(self.package_version, "notification package version")
        if not isinstance(self.package_fingerprint, PreviewFingerprint):
            object.__setattr__(self, "package_fingerprint", PreviewFingerprint(self.package_fingerprint))
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("notification idempotency key must be IdempotencyKey")


@dataclass(frozen=True, slots=True)
class MatchingCriteriaRecontactIntentProjection:
    """Immutable G1/G2 recontact intent; LINE owns delivery after commit."""

    intent_id: str
    recipient_subject_reference: str
    candidate_id: str
    staff_id: int
    route_group: RefusalRoutingGroup
    action: str
    reason_code: str
    before_snapshot_id: str
    after_snapshot_id: str
    diff_fingerprint: PreviewFingerprint
    source_versions: MatchingSourceTuple
    idempotency_key: IdempotencyKey
    package_id: str | None = None
    package_version: int | None = None
    package_fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.intent_id, "criteria recontact intent ID"),
            (self.recipient_subject_reference, "recontact recipient subject reference"),
            (self.candidate_id, "recontact candidate ID"),
            (self.reason_code, "recontact reason code"),
            (self.before_snapshot_id, "recontact before snapshot ID"),
            (self.after_snapshot_id, "recontact after snapshot ID"),
        ):
            require_canonical_text(value, name, 191)
        if isinstance(self.staff_id, bool) or not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("recontact staff ID must be positive")
        if not isinstance(self.route_group, RefusalRoutingGroup):
            object.__setattr__(self, "route_group", RefusalRoutingGroup(self.route_group))
        expected_action = {
            RefusalRoutingGroup.GROUP1_ORIGINAL_WILLING_RECONFIRM: "reconfirm",
            RefusalRoutingGroup.GROUP2_PAIN_RESOLVED_REPROBE: "reprobe",
        }.get(self.route_group)
        if self.action != expected_action:
            raise ValueError("recontact action must match a G1 or G2 route")
        if not isinstance(self.diff_fingerprint, PreviewFingerprint):
            object.__setattr__(self, "diff_fingerprint", PreviewFingerprint(self.diff_fingerprint))
        _validate_sources(self.source_versions)
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("recontact idempotency key must be IdempotencyKey")
        package_values = (self.package_id, self.package_version, self.package_fingerprint)
        if any(value is not None for value in package_values):
            if any(value is None for value in package_values):
                raise ValueError("recontact package lineage must be complete")
            require_canonical_text(self.package_id, "recontact package ID", 191)  # type: ignore[arg-type]
            require_nonnegative_integer(self.package_version, "recontact package version")  # type: ignore[arg-type]
            if not isinstance(self.package_fingerprint, PreviewFingerprint):
                object.__setattr__(self, "package_fingerprint", PreviewFingerprint(self.package_fingerprint))


@dataclass(frozen=True, slots=True)
class ZeroCandidateAlternativeView:
    alternative_id: str
    policy_id: str
    policy_version: int
    relaxed_criteria: tuple[str, ...]
    unchanged_hard_criteria: tuple[str, ...]
    candidate_result: MatchingCandidateResultView | None
    risk_warnings: tuple[str, ...]
    deterministic_rank: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class MatchingDecisionView:
    event_id: str
    case_no: str
    package_id: str
    package_version: int
    candidate_id: str | None
    actor_id: str
    customer_state: str
    caregiver_state: str
    fresh_effects_status: str
    accepted_is_not_contract_or_assignment: bool
    rematch_reference: str | None
    source_versions: MatchingSourceTuple
    conversion_request: MatchingCrossDomainRequest | None = None


@dataclass(frozen=True, slots=True)
class MatchingApplyReceipt:
    receipt_id: str
    command_name: MatchingCommandName
    command_fingerprint: PreviewFingerprint
    preview_fingerprint: PreviewFingerprint
    source_versions: MatchingSourceTuple
    decision_event_id: str | None
    package_id: str | None
    outbox_intent_ids: tuple[str, ...]
    result_state: str
    cross_domain_request: MatchingCrossDomainRequest | None = None
    zero_candidate_decision: ZeroCandidateDecisionLineage | None = None
    willingness_lineage: DynamicWillingnessLineage | None = None
    notification_intents: tuple[MatchingNotificationIntentProjection, ...] = ()
    criteria_recontact_intents: tuple[MatchingCriteriaRecontactIntentProjection, ...] = ()


def snapshot_view(snapshot: MatchingCriteriaSnapshot) -> MatchingCriteriaSnapshotView:
    return MatchingCriteriaSnapshotView(
        snapshot.snapshot_id,
        snapshot.case_no,
        snapshot.criteria_version,
        tuple(
            (key, _transport_criteria_value(value))
            for key, value in sorted(snapshot.criteria.items())
        ),
        snapshot.source_versions,
        snapshot.fingerprint,
        snapshot.created_at,
        snapshot.superseded_by,
    )


def _transport_criteria_value(value: Any) -> Any:
    """Thaw immutable criteria only at the transport boundary."""

    if isinstance(value, Mapping):
        return {key: _transport_criteria_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_transport_criteria_value(item) for item in value)
    return value


def candidate_view(candidate: MatchingCandidateResult) -> MatchingCandidateResultView:
    return MatchingCandidateResultView(candidate.candidate_id, candidate.staff_id, candidate.eligibility, tuple(MatchingCriteriaResultView(item.code, item.status, item.source_version, item.detail) for item in candidate.criteria_results), candidate.rejection_reasons, candidate.coverage_evidence, candidate.willingness, candidate.notification_lineage, candidate.staff_name)


def package_view(package: MatchingPackage) -> MatchingPackageView:
    return MatchingPackageView(package.package_id, package.version, package.mode, tuple((item.staff_id, item.service_dates, item.sequence) for item in package.segments), package.required_service_dates, tuple(candidate_view(item) for item in package.candidate_results), package.criteria_snapshot_id, package.source_versions, package.blockers, package.warnings, package.state, package.fingerprint)


def criteria_diff_view(diff: MatchingCriteriaDiff) -> CriteriaDiffView:
    return CriteriaDiffView(diff.before_snapshot_id, diff.after_snapshot_id, diff.added, diff.removed, diff.changed, diff.unchanged, diff.affected_candidate_ids, diff.affected_recipient_ids, diff.resend_eligible, diff.fingerprint, diff.refusal_routes)


def alternative_view(alternative: ZeroCandidateAlternative) -> ZeroCandidateAlternativeView:
    return ZeroCandidateAlternativeView(alternative.alternative_id, alternative.policy_id, alternative.policy_version, alternative.relaxed_criteria, alternative.unchanged_hard_criteria, candidate_view(alternative.candidate_result) if alternative.candidate_result else None, alternative.risk_warnings, alternative.deterministic_rank, alternative.preview_fingerprint)


def decision_view(lineage: MatchingDecisionLineage) -> MatchingDecisionView:
    return MatchingDecisionView(lineage.event_id, lineage.case_no, lineage.package_id, lineage.package_version, lineage.candidate_id, lineage.actor_id, lineage.customer_state, lineage.caregiver_state, lineage.fresh_effects_status, lineage.accepted_is_not_contract_or_assignment, lineage.rematch_reference, lineage.source_versions, lineage.conversion_request)


def typed_error(code: MatchingErrorCode | str, correlation_id: CorrelationId, *, category: ErrorCategory = ErrorCategory.DOMAIN_BLOCKED, retryable: bool = False, blockers: tuple[str, ...] = ()) -> TypedError:
    return TypedError(category, str(code), str(code), correlation_id, domain_blockers=tuple(sorted(set(blockers))), retryable=retryable)


def command_fingerprint(command: MatchingCommand) -> PreviewFingerprint:
    return fingerprint_payload({"command": _canonical_command_value(command)})


def _canonical_command_value(value: Any) -> Any:
    """Convert a frozen typed command to the canonical fingerprint payload."""

    if isinstance(value, PreviewFingerprint):
        return value.value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_canonical_command_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_command_value(item) for item in value]
    if isinstance(value, MatchingSourceVersion):
        return list(value.as_payload())
    if isinstance(value, CorrelationId):
        return value.value
    if isinstance(value, IdempotencyKey):
        return value.value
    if isinstance(value, ActorContext):
        return {"actor_id": value.actor_id}
    if is_dataclass(value):
        return {field.name: _canonical_command_value(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"unsupported command fingerprint value: {type(value).__name__}")


def _validate_sources(value: object) -> None:
    from domains.scheduling.matching_coordination import canonical_source_tuple

    canonical_source_tuple(value)  # type: ignore[arg-type]


__all__ = [
    "ApplyInitialCriteriaSnapshot",
    "ApplyCaregiverSelection",
    "ApplyCriteriaDiffResend",
    "ApplyCustomerMatchingDecision",
    "ApplyLeaveImpactOnMatching",
    "ApplyRematch",
    "ApplyServiceDateChangeRematch",
    "ApplyZeroCandidateAlternative",
    "CriteriaDiffView",
    "DynamicWillingnessLineage",
    "MatchingApplyReceipt",
    "MatchingCandidateResultView",
    "MatchingCommand",
    "MatchingCommandName",
    "MatchingCrossDomainRequest",
    "MatchingCriteriaResultView",
    "MatchingCriteriaSnapshotView",
    "MatchingDecisionView",
    "MatchingErrorCode",
    "MatchingNotificationIntentProjection",
    "MatchingNotificationRecipientRole",
    "MatchingPackageView",
    "MATCHING_ERROR_CODES",
    "PreviewCriteriaDiffResend",
    "PreviewInitialCriteriaSnapshot",
    "PreviewLeaveImpactOnMatching",
    "PreviewMatchingPackage",
    "PreviewRematch",
    "PreviewServiceDateChangeRematch",
    "PreviewZeroCandidateAlternative",
    "QueryMatchingCoordination",
    "ZeroCandidateAlternativeView",
    "ZeroCandidateDecisionLineage",
    "alternative_view",
    "candidate_view",
    "command_fingerprint",
    "criteria_diff_view",
    "decision_view",
    "package_view",
    "snapshot_view",
    "typed_error",
]

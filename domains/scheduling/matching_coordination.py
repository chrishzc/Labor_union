"""
File: matching_coordination.py
Description: 定義 Scheduling Matching Coordination 的不可變事實與純規則。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


SOURCE_KINDS: tuple[str, ...] = (
    "orders_terms",
    "orders_service_dates",
    "scheduling_availability",
    "scheduling_effective_generation",
    "staff_profile_definition",
    "staff_profile_values",
    "staff_lifecycle",
    "matching_criteria_snapshot",
    "candidate_pool",
    "matching_package",
    "incumbent_assignment",
    "leave_request_or_outcome",
    "assignment_conversion_reference",
)
_MAXIMUM_IDENTITY_LENGTH = 191
_MAXIMUM_REASON_LENGTH = 500


class MatchingDomainErrorCode(StrEnum):
    INVALID = "matching_criteria_invalid"
    COVERAGE_INCOMPLETE = "matching_coverage_incomplete"
    SOURCE_CONFLICT = "matching_source_version_conflict"
    NO_CANDIDATE = "matching_no_candidate"
    ALTERNATIVE_REQUIRED = "matching_alternative_not_explicit"
    REMATCH_REQUIRED = "matching_rematch_required"
    CUSTOMER_ACCEPTANCE_NOT_CONVERSION = "matching_customer_acceptance_not_conversion"


class MatchingDomainError(ValueError):
    """純 domain validation 的 machine-stable error。"""

    def __init__(self, code: MatchingDomainErrorCode | str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


class CriterionStatus(StrEnum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    SOURCE_NOT_READY = "source_not_ready"
    NOT_CONSULTED = "not_consulted"


class CandidateEligibility(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    EXPIRED = "expired"
    STALE = "stale"


class StableRejectionReason(StrEnum):
    """Machine-stable candidate/refusal reason codes from the M3 contract."""

    REGION_MISMATCH = "region_mismatch"
    SERVICE_DATE_CONFLICT = "service_date_conflict"
    UNAVAILABLE_PERIOD = "unavailable_period"
    WAITING_LOCK_CONFLICT = "waiting_lock_conflict"
    BUFFER_CONFLICT = "buffer_conflict"
    STAFF_RETIRED = "staff_retired"
    PREFERENCE_NOT_READY = "preference_not_ready"
    PREFERENCE_MISMATCH = "preference_mismatch"
    COVERAGE_INCOMPLETE = "coverage_incomplete"
    LINE_BINDING_MISSING = "line_binding_missing"
    WILLINGNESS_UNCONFIRMED = "willingness_unconfirmed"
    INCUMBENT_OCCUPIED = "incumbent_occupied"
    DUE_DATE_OUTSIDE_WINDOW = "due_date_outside_window"
    CRITERIA_SOURCE_STALE = "criteria_source_stale"
    CANDIDATE_EXPIRED = "candidate_expired"


class RefusalRoutingGroup(StrEnum):
    """Deterministic routing groups for a criteria-change recontact."""

    GROUP1_ORIGINAL_WILLING_RECONFIRM = "group1_original_willing_reconfirm"
    GROUP2_PAIN_RESOLVED_REPROBE = "group2_pain_resolved_reprobe"
    GROUP3_UNRELATED_SILENT_EXCLUDE = "group3_unrelated_silent_exclude"


class WillingnessState(StrEnum):
    """A contact state is scoped to one criteria snapshot, never permanent."""

    UNCONFIRMED = "unconfirmed"
    PENDING = "pending"
    WILLING = "willing"
    UNWILLING = "unwilling"
    EXPIRED = "expired"
    STALE = "stale"
    RECONTACT_PREVIEWED = "recontact_previewed"
    RECONTACT_QUEUED = "recontact_queued"
    SILENT_EXCLUDED = "silent_excluded"


class ZeroCandidateDecision(StrEnum):
    AGREE = "agree"
    DISAGREE = "disagree"


class MatchingRequestKind(StrEnum):
    ASSIGNMENT_CONVERSION_REQUESTED = "assignment_conversion_requested"
    REMATCH_REQUESTED = "rematch_requested"


class MatchingPackageMode(StrEnum):
    SINGLE = "single"
    MULTI_SEGMENT = "multi_segment"


class MatchingPackageState(StrEnum):
    PROPOSED = "proposed"
    AWAITING_CAREGIVER_WILLINGNESS = "awaiting_caregiver_willingness"
    AWAITING_CUSTOMER_DECISION = "awaiting_customer_decision"
    NO_CANDIDATE = "no_candidate"
    REMATCH_REQUIRED = "rematch_required"


@dataclass(frozen=True, slots=True)
class MatchingSourceVersion:
    source_kind: str
    source_id: str
    version: int | str
    fingerprint: str | PreviewFingerprint

    def __post_init__(self) -> None:
        require_canonical_text(self.source_kind, "source kind", 80)
        require_canonical_text(self.source_id, "source id", _MAXIMUM_IDENTITY_LENGTH)
        if self.source_kind not in SOURCE_KINDS:
            raise MatchingDomainError(MatchingDomainErrorCode.SOURCE_CONFLICT, "unknown matching source kind")
        if self.source_id == "not_consulted":
            if self.version != "not_consulted" or self.fingerprint != "not_consulted":
                raise MatchingDomainError(MatchingDomainErrorCode.SOURCE_CONFLICT, "not_consulted source must be explicit")
            return
        if isinstance(self.version, bool) or not isinstance(self.version, (int, str)):
            raise TypeError("source version must be an integer or canonical string")
        if isinstance(self.version, int):
            require_nonnegative_integer(self.version, "source version")
        else:
            require_canonical_text(self.version, "source version", _MAXIMUM_IDENTITY_LENGTH)
        fingerprint = self.fingerprint.value if isinstance(self.fingerprint, PreviewFingerprint) else self.fingerprint
        object.__setattr__(self, "fingerprint", fingerprint)
        require_canonical_text(fingerprint, "source fingerprint", 128)
        if len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
            raise ValueError("source fingerprint must be a lowercase SHA-256 digest")

    @classmethod
    def not_consulted(cls, source_kind: str) -> "MatchingSourceVersion":
        return cls(source_kind, "not_consulted", "not_consulted", "not_consulted")

    def as_payload(self) -> tuple[str, str, int | str, str]:
        return (self.source_kind, self.source_id, self.version, self.fingerprint)


MatchingSourceTuple = tuple[MatchingSourceVersion, ...]


def canonical_source_tuple(items: Sequence[MatchingSourceVersion]) -> MatchingSourceTuple:
    """建立完整且固定順序的 13 項 source-version tuple。"""
    if not isinstance(items, (tuple, list)):
        raise TypeError("matching source tuple must be a tuple or list")
    by_kind = {item.source_kind: item for item in items}
    if len(by_kind) != len(items) or set(by_kind) != set(SOURCE_KINDS):
        raise MatchingDomainError(MatchingDomainErrorCode.SOURCE_CONFLICT, "matching source tuple must contain every source kind")
    return tuple(by_kind[kind] for kind in SOURCE_KINDS)


@dataclass(frozen=True, slots=True)
class MatchingCriteriaResult:
    code: str
    status: CriterionStatus
    source_version: MatchingSourceVersion
    detail: str = ""

    def __post_init__(self) -> None:
        require_canonical_text(self.code, "criteria result code", 80)
        if not isinstance(self.status, CriterionStatus):
            object.__setattr__(self, "status", CriterionStatus(self.status))
        if self.source_version.source_kind not in SOURCE_KINDS:
            raise MatchingDomainError(MatchingDomainErrorCode.SOURCE_CONFLICT, "criteria source is invalid")
        if self.detail:
            require_canonical_text(self.detail, "criteria result detail", _MAXIMUM_REASON_LENGTH)


@dataclass(frozen=True, slots=True)
class MatchingCriteriaSnapshot:
    snapshot_id: str
    case_no: str
    criteria_version: int
    criteria: Mapping[str, Any]
    source_versions: MatchingSourceTuple
    fingerprint: PreviewFingerprint
    created_at: datetime
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        _validate_identity(self.snapshot_id, "snapshot id")
        _validate_identity(self.case_no, "case number", 50)
        require_nonnegative_integer(self.criteria_version, "criteria version")
        if not isinstance(self.criteria, Mapping):
            raise TypeError("criteria must be a mapping")
        frozen_criteria = {key: _freeze_value(value) for key, value in self.criteria.items()}
        if any(not isinstance(key, str) for key in frozen_criteria):
            raise TypeError("criteria keys must be strings")
        object.__setattr__(self, "criteria", MappingProxyType(frozen_criteria))
        object.__setattr__(self, "source_versions", canonical_source_tuple(self.source_versions))
        if not isinstance(self.fingerprint, PreviewFingerprint):
            object.__setattr__(self, "fingerprint", PreviewFingerprint(self.fingerprint))
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.superseded_by is not None:
            _validate_identity(self.superseded_by, "superseded snapshot id")
        expected = fingerprint_payload(self.canonical_payload())
        if self.fingerprint != expected:
            raise ValueError("criteria snapshot fingerprint does not match immutable identity")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "case_no": self.case_no,
            "criteria": dict(self.criteria),
            "criteria_version": self.criteria_version,
            "source_versions": [item.as_payload() for item in self.source_versions],
        }


@dataclass(frozen=True, slots=True)
class MatchingCandidateResult:
    candidate_id: str
    staff_id: int
    eligibility: CandidateEligibility
    criteria_results: tuple[MatchingCriteriaResult, ...]
    rejection_reasons: tuple[str, ...] = ()
    coverage_evidence: tuple[date, ...] = ()
    willingness: str = "unconfirmed"
    notification_lineage: tuple[str, ...] = ()
    staff_name: str = ""

    def __post_init__(self) -> None:
        _validate_identity(self.candidate_id, "candidate id")
        if isinstance(self.staff_id, bool) or not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("staff id must be positive")
        if not isinstance(self.eligibility, CandidateEligibility):
            object.__setattr__(self, "eligibility", CandidateEligibility(self.eligibility))
        _validate_tuple(self.criteria_results, MatchingCriteriaResult, "criteria results")
        object.__setattr__(self, "rejection_reasons", _normalize_stable_reason_codes(self.rejection_reasons, "candidate rejection reasons"))
        _validate_dates(self.coverage_evidence, "coverage evidence")
        _validate_text_tuple(self.notification_lineage, "notification lineage")
        require_canonical_text(self.willingness, "willingness", 40)
        if not isinstance(self.willingness, WillingnessState):
            try:
                object.__setattr__(self, "willingness", WillingnessState(self.willingness))
            except ValueError as exc:
                raise ValueError("willingness is not a supported state") from exc
        if self.staff_name:
            require_canonical_text(self.staff_name, "staff name", 100)


@dataclass(frozen=True, slots=True)
class RefusalHistoryEntry:
    """Immutable refusal evidence used by the criteria-diff router.

    ``affected_criteria`` is the stable projection of the criteria that caused
    the refusal.  ``pain_resolved`` is supplied by the owning refusal history
    source; the coordinator never guesses from free-form text.
    """

    refusal_id: str
    candidate_id: str
    snapshot_id: str
    reason_code: str
    affected_criteria: tuple[str, ...] = ()
    originally_willing: bool = False
    pain_resolved: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.refusal_id, "refusal id"),
            (self.candidate_id, "candidate id"),
            (self.snapshot_id, "refusal snapshot id"),
        ):
            _validate_identity(value, name)
        object.__setattr__(self, "reason_code", _normalize_stable_reason_code(self.reason_code, "refusal reason code"))
        _validate_text_tuple(self.affected_criteria, "affected criteria")
        if not isinstance(self.originally_willing, bool) or not isinstance(self.pain_resolved, bool):
            raise TypeError("refusal routing flags must be bool")


# Friendly alias used by subsystem callers that name this projection history.
MatchingRefusalHistory = RefusalHistoryEntry


@dataclass(frozen=True, slots=True)
class RefusalRouting:
    candidate_id: str
    refusal_id: str
    group: RefusalRoutingGroup
    action: str
    reason_code: str
    source_snapshot_id: str
    diff_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        for value, name in (
            (self.candidate_id, "candidate id"),
            (self.refusal_id, "refusal id"),
            (self.source_snapshot_id, "source snapshot id"),
            (self.action, "refusal routing action"),
        ):
            _validate_identity(value, name)
        object.__setattr__(self, "reason_code", _normalize_stable_reason_code(self.reason_code, "refusal reason code"))
        if not isinstance(self.group, RefusalRoutingGroup):
            object.__setattr__(self, "group", RefusalRoutingGroup(self.group))
        if not isinstance(self.diff_fingerprint, PreviewFingerprint):
            object.__setattr__(self, "diff_fingerprint", PreviewFingerprint(self.diff_fingerprint))


MatchingRefusalRoute = RefusalRouting


@dataclass(frozen=True, slots=True)
class DynamicWillingnessLineage:
    """Append-only willingness observation tied to one snapshot and source tuple."""

    event_id: str
    candidate_id: str
    staff_id: int
    snapshot_id: str
    source_versions: MatchingSourceTuple
    previous_state: str
    current_state: str
    reason_code: str | None = None
    affected_criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in ((self.event_id, "willingness event id"), (self.candidate_id, "candidate id"), (self.snapshot_id, "willingness snapshot id")):
            _validate_identity(value, name)
        if isinstance(self.staff_id, bool) or not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("willingness staff id must be positive")
        object.__setattr__(self, "source_versions", canonical_source_tuple(self.source_versions))
        for value, name in ((self.previous_state, "previous willingness state"), (self.current_state, "current willingness state")):
            require_canonical_text(value, name, 40)
            try:
                WillingnessState(value)
            except ValueError as exc:
                raise ValueError(f"{name} is not a supported state") from exc
        transition = (
            WillingnessState(self.previous_state),
            WillingnessState(self.current_state),
        )
        allowed_transitions = {
            (WillingnessState.UNCONFIRMED, WillingnessState.PENDING),
            (WillingnessState.PENDING, WillingnessState.WILLING),
            (WillingnessState.PENDING, WillingnessState.UNWILLING),
            (WillingnessState.PENDING, WillingnessState.EXPIRED),
            (WillingnessState.WILLING, WillingnessState.STALE),
            (WillingnessState.UNWILLING, WillingnessState.STALE),
            (WillingnessState.EXPIRED, WillingnessState.STALE),
            (WillingnessState.STALE, WillingnessState.RECONTACT_PREVIEWED),
            (WillingnessState.STALE, WillingnessState.SILENT_EXCLUDED),
            (
                WillingnessState.RECONTACT_PREVIEWED,
                WillingnessState.RECONTACT_QUEUED,
            ),
            (WillingnessState.RECONTACT_QUEUED, WillingnessState.PENDING),
        }
        if transition not in allowed_transitions:
            raise ValueError("willingness transition is not supported")
        object.__setattr__(self, "affected_criteria", tuple(sorted(set(self.affected_criteria))))
        _validate_text_tuple(self.affected_criteria, "willingness affected criteria")
        if not self.affected_criteria:
            raise ValueError("willingness affected criteria are required")
        if self.reason_code is not None:
            object.__setattr__(self, "reason_code", _normalize_stable_reason_code(self.reason_code, "willingness reason code"))
        if self.current_state == WillingnessState.WILLING.value and self.reason_code is not None:
            raise ValueError("willing willingness event cannot carry refusal reason")
        if self.current_state == WillingnessState.UNWILLING.value and self.reason_code is None:
            raise ValueError("unwilling willingness event requires stable reason")


@dataclass(frozen=True, slots=True)
class ZeroCandidateDecisionLineage:
    event_id: str
    case_no: str
    alternative_id: str
    policy_id: str
    policy_version: int
    decision: ZeroCandidateDecision
    outcome_state: str
    actor_id: str
    source_versions: MatchingSourceTuple
    assignment_request_id: str | None = None

    def __post_init__(self) -> None:
        for value, name in ((self.event_id, "zero-candidate event id"), (self.case_no, "case number"), (self.alternative_id, "alternative id"), (self.policy_id, "policy id"), (self.outcome_state, "zero-candidate outcome"), (self.actor_id, "actor id")):
            _validate_identity(value, name)
        require_nonnegative_integer(self.policy_version, "policy version")
        if not isinstance(self.decision, ZeroCandidateDecision):
            object.__setattr__(self, "decision", ZeroCandidateDecision(self.decision))
        object.__setattr__(self, "source_versions", canonical_source_tuple(self.source_versions))
        if self.assignment_request_id is not None:
            _validate_identity(self.assignment_request_id, "assignment request id")


@dataclass(frozen=True, slots=True)
class MatchingCrossDomainRequest:
    """Typed projection to an owning workflow; it never writes that root."""

    request_id: str
    request_kind: MatchingRequestKind
    case_no: str
    package_id: str
    package_version: int
    criteria_snapshot_id: str
    candidate_id: str | None
    source_versions: MatchingSourceTuple
    lineage_event_id: str
    reason: str

    def __post_init__(self) -> None:
        for value, name in ((self.request_id, "cross-domain request id"), (self.case_no, "case number"), (self.package_id, "package id"), (self.criteria_snapshot_id, "criteria snapshot id"), (self.lineage_event_id, "lineage event id"), (self.reason, "request reason")):
            _validate_identity(value, name, 500 if name == "request reason" else _MAXIMUM_IDENTITY_LENGTH)
        if self.candidate_id is not None:
            _validate_identity(self.candidate_id, "candidate id")
        require_nonnegative_integer(self.package_version, "package version")
        if not isinstance(self.request_kind, MatchingRequestKind):
            object.__setattr__(self, "request_kind", MatchingRequestKind(self.request_kind))
        object.__setattr__(self, "source_versions", canonical_source_tuple(self.source_versions))


AssignmentConversionRequest = MatchingCrossDomainRequest
RematchRequest = MatchingCrossDomainRequest


@dataclass(frozen=True, slots=True)
class MatchingSegment:
    staff_id: int
    service_dates: tuple[date, ...]
    sequence: int

    def __post_init__(self) -> None:
        if isinstance(self.staff_id, bool) or not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("segment staff id must be positive")
        require_nonnegative_integer(self.sequence, "segment sequence")
        if self.sequence <= 0:
            raise ValueError("segment sequence must be positive")
        _validate_dates(self.service_dates, "segment service dates")


@dataclass(frozen=True, slots=True)
class MatchingPackage:
    package_id: str
    version: int
    mode: MatchingPackageMode
    segments: tuple[MatchingSegment, ...]
    required_service_dates: tuple[date, ...]
    candidate_results: tuple[MatchingCandidateResult, ...]
    criteria_snapshot_id: str
    source_versions: MatchingSourceTuple
    state: MatchingPackageState = MatchingPackageState.PROPOSED
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        _validate_identity(self.package_id, "package id")
        require_nonnegative_integer(self.version, "package version")
        if not isinstance(self.mode, MatchingPackageMode):
            object.__setattr__(self, "mode", MatchingPackageMode(self.mode))
        if not isinstance(self.segments, tuple) or any(not isinstance(item, MatchingSegment) for item in self.segments):
            raise TypeError("package segments must be typed tuple")
        if not self.segments and self.state is not MatchingPackageState.NO_CANDIDATE:
            raise MatchingDomainError(MatchingDomainErrorCode.COVERAGE_INCOMPLETE, "package requires segments")
        _validate_dates(self.required_service_dates, "required service dates")
        _validate_tuple(self.candidate_results, MatchingCandidateResult, "candidate results")
        _validate_identity(self.criteria_snapshot_id, "criteria snapshot id")
        object.__setattr__(self, "source_versions", canonical_source_tuple(self.source_versions))
        if not isinstance(self.state, MatchingPackageState):
            object.__setattr__(self, "state", MatchingPackageState(self.state))
        _validate_reason_codes(self.blockers)
        _validate_reason_codes(self.warnings)
        _validate_package_coverage(self)
        expected_fingerprint = fingerprint_payload(self.canonical_payload())
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected_fingerprint)
        else:
            supplied_fingerprint = (
                self.fingerprint
                if isinstance(self.fingerprint, PreviewFingerprint)
                else PreviewFingerprint(self.fingerprint)
            )
            if supplied_fingerprint != expected_fingerprint:
                raise ValueError(
                    "matching package fingerprint does not match immutable identity"
                )
            object.__setattr__(self, "fingerprint", supplied_fingerprint)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "candidate_results": tuple(_candidate_payload(item) for item in self.candidate_results),
            "criteria_snapshot_id": self.criteria_snapshot_id,
            "mode": self.mode.value,
            "package_id": self.package_id,
            "required_service_dates": tuple(item.isoformat() for item in self.required_service_dates),
            "segments": tuple((item.staff_id, item.sequence, tuple(day.isoformat() for day in item.service_dates)) for item in self.segments),
            "source_versions": tuple(item.as_payload() for item in self.source_versions),
            "state": self.state.value,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class MatchingCriteriaDiff:
    before_snapshot_id: str
    after_snapshot_id: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]
    affected_candidate_ids: tuple[str, ...]
    affected_recipient_ids: tuple[str, ...]
    resend_eligible: bool
    fingerprint: PreviewFingerprint
    refusal_routes: tuple[RefusalRouting, ...] = ()

    def __post_init__(self) -> None:
        _validate_identity(self.before_snapshot_id, "before snapshot id")
        _validate_identity(self.after_snapshot_id, "after snapshot id")
        for name in ("added", "removed", "changed", "unchanged", "affected_candidate_ids", "affected_recipient_ids"):
            _validate_text_tuple(getattr(self, name), name)
        if not isinstance(self.resend_eligible, bool):
            raise TypeError("resend_eligible must be bool")
        if not isinstance(self.fingerprint, PreviewFingerprint):
            object.__setattr__(self, "fingerprint", PreviewFingerprint(self.fingerprint))
        _validate_tuple(self.refusal_routes, RefusalRouting, "refusal routes")


@dataclass(frozen=True, slots=True)
class ZeroCandidateAlternative:
    alternative_id: str
    policy_id: str
    policy_version: int
    relaxed_criteria: tuple[str, ...]
    unchanged_hard_criteria: tuple[str, ...]
    candidate_result: MatchingCandidateResult | None
    risk_warnings: tuple[str, ...]
    deterministic_rank: int
    preview_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        for value, name in ((self.alternative_id, "alternative id"), (self.policy_id, "policy id")):
            _validate_identity(value, name)
        require_nonnegative_integer(self.policy_version, "policy version")
        _validate_text_tuple(self.relaxed_criteria, "relaxed criteria")
        _validate_text_tuple(self.unchanged_hard_criteria, "unchanged hard criteria")
        _validate_reason_codes(self.risk_warnings)
        if self.deterministic_rank <= 0:
            raise ValueError("deterministic rank must be positive")
        if not isinstance(self.preview_fingerprint, PreviewFingerprint):
            object.__setattr__(self, "preview_fingerprint", PreviewFingerprint(self.preview_fingerprint))


@dataclass(frozen=True, slots=True)
class MatchingDecisionLineage:
    event_id: str
    case_no: str
    package_id: str
    package_version: int
    candidate_id: str | None
    actor_id: str
    customer_state: str
    caregiver_state: str
    fresh_effects_status: str
    rematch_reference: str | None = None
    source_versions: MatchingSourceTuple = ()
    conversion_request: MatchingCrossDomainRequest | None = None

    def __post_init__(self) -> None:
        for value, name in ((self.event_id, "event id"), (self.case_no, "case number"), (self.package_id, "package id"), (self.actor_id, "actor id"), (self.customer_state, "customer state"), (self.caregiver_state, "caregiver state"), (self.fresh_effects_status, "fresh effects status")):
            _validate_identity(value, name, 500 if name == "fresh effects status" else _MAXIMUM_IDENTITY_LENGTH)
        if self.candidate_id is not None:
            _validate_identity(self.candidate_id, "candidate id")
        require_nonnegative_integer(self.package_version, "package version")
        if self.rematch_reference is not None:
            _validate_identity(self.rematch_reference, "rematch reference")
        if self.source_versions:
            object.__setattr__(self, "source_versions", canonical_source_tuple(self.source_versions))
        if self.conversion_request is not None and self.conversion_request.case_no != self.case_no:
            raise MatchingDomainError(MatchingDomainErrorCode.SOURCE_CONFLICT, "conversion request case does not match decision")

    @property
    def accepted_is_not_contract_or_assignment(self) -> bool:
        return True


def build_criteria_snapshot(
    *,
    snapshot_id: str,
    case_no: str,
    criteria_version: int,
    criteria: Mapping[str, Any],
    source_versions: Sequence[MatchingSourceVersion],
    created_at: datetime,
) -> MatchingCriteriaSnapshot:
    source_tuple = canonical_source_tuple(source_versions)
    payload = {
        "case_no": case_no,
        "criteria": dict(criteria),
        "criteria_version": criteria_version,
        "source_versions": tuple(item.as_payload() for item in source_tuple),
    }
    return MatchingCriteriaSnapshot(snapshot_id, case_no, criteria_version, criteria, source_tuple, fingerprint_payload(payload), created_at)


def build_criteria_diff(
    before: MatchingCriteriaSnapshot,
    after: MatchingCriteriaSnapshot,
    candidates: Sequence[MatchingCandidateResult] = (),
    refusal_history: Sequence[RefusalHistoryEntry] = (),
    willingness_lineage: Sequence[DynamicWillingnessLineage] = (),
) -> MatchingCriteriaDiff:
    before_keys = set(before.criteria)
    after_keys = set(after.criteria)
    added = tuple(sorted(after_keys - before_keys))
    removed = tuple(sorted(before_keys - after_keys))
    changed = tuple(sorted(key for key in before_keys & after_keys if before.criteria[key] != after.criteria[key]))
    unchanged = tuple(sorted(key for key in before_keys & after_keys if before.criteria[key] == after.criteria[key]))
    impact_history = (
        _candidate_impact_history(
            before,
            candidates,
            refusal_history,
            willingness_lineage,
        )
        if added or removed or changed
        else ()
    )
    routes = route_refusal_history(before, after, impact_history) if impact_history else ()
    route_by_candidate = {item.candidate_id: item for item in routes}
    affected = tuple(sorted({item.candidate_id for item in candidates if item.rejection_reasons or item.eligibility is not CandidateEligibility.ELIGIBLE} | set(route_by_candidate)))
    recipients = tuple(
        sorted(
            {
                item.candidate_id
                for item in candidates
                if item.eligibility is CandidateEligibility.ELIGIBLE
                and route_by_candidate.get(item.candidate_id) is not None
                and route_by_candidate[item.candidate_id].group
                in {
                    RefusalRoutingGroup.GROUP1_ORIGINAL_WILLING_RECONFIRM,
                    RefusalRoutingGroup.GROUP2_PAIN_RESOLVED_REPROBE,
                }
            }
        )
    )
    payload = {"after": after.fingerprint.value, "before": before.fingerprint.value, "added": added, "changed": changed, "removed": removed, "unchanged": unchanged, "affected": affected, "recipients": recipients, "refusal_routes": tuple((item.candidate_id, item.group.value, item.action, item.reason_code) for item in routes)}
    return MatchingCriteriaDiff(before.snapshot_id, after.snapshot_id, added, removed, changed, unchanged, affected, recipients, bool(recipients), fingerprint_payload(payload), routes)


def _candidate_impact_history(
    before: MatchingCriteriaSnapshot,
    candidates: Sequence[MatchingCandidateResult],
    refusal_history: Sequence[RefusalHistoryEntry],
    willingness_lineage: Sequence[DynamicWillingnessLineage],
) -> tuple[RefusalHistoryEntry, ...]:
    """Project latest before-snapshot willingness events into routing evidence."""

    explicit = tuple(refusal_history)
    if any(not isinstance(item, RefusalHistoryEntry) for item in explicit):
        raise TypeError("refusal history must contain typed entries")
    if any(item.snapshot_id != before.snapshot_id for item in explicit):
        raise MatchingDomainError(
            MatchingDomainErrorCode.SOURCE_CONFLICT,
            "candidate impact lineage references the wrong snapshot",
        )
    explicit_candidates = tuple(item.candidate_id for item in explicit)
    if len(explicit_candidates) != len(set(explicit_candidates)):
        raise MatchingDomainError(
            MatchingDomainErrorCode.SOURCE_CONFLICT,
            "candidate impact lineage is ambiguous",
        )
    latest: dict[str, DynamicWillingnessLineage] = {}
    for event in willingness_lineage:
        if not isinstance(event, DynamicWillingnessLineage):
            raise TypeError("willingness lineage must contain typed events")
        if event.snapshot_id == before.snapshot_id:
            if event.candidate_id in latest:
                raise MatchingDomainError(
                    MatchingDomainErrorCode.SOURCE_CONFLICT,
                    "candidate impact lineage is ambiguous",
                )
            latest[event.candidate_id] = event
    candidate_by_id = {item.candidate_id: item for item in candidates}
    if len(candidate_by_id) != len(candidates) or set(explicit_candidates) & set(latest):
        raise MatchingDomainError(
            MatchingDomainErrorCode.SOURCE_CONFLICT,
            "candidate impact lineage is ambiguous",
        )
    covered = {item.candidate_id for item in explicit} | set(latest)
    missing = set(candidate_by_id) - covered
    if missing:
        raise MatchingDomainError(
            MatchingDomainErrorCode.SOURCE_CONFLICT,
            "candidate impact lineage is incomplete",
        )
    projected: list[RefusalHistoryEntry] = list(explicit)
    for candidate_id, event in latest.items():
        candidate = candidate_by_id.get(candidate_id)
        originally_willing = event.current_state == WillingnessState.WILLING.value
        old_reason = event.reason_code or StableRejectionReason.WILLINGNESS_UNCONFIRMED.value
        pain_resolved = bool(
            event.current_state == WillingnessState.UNWILLING.value
            and candidate is not None
            and candidate.eligibility is CandidateEligibility.ELIGIBLE
            and old_reason not in candidate.rejection_reasons
        )
        projected.append(
            RefusalHistoryEntry(
                event.event_id,
                event.candidate_id,
                event.snapshot_id,
                old_reason,
                event.affected_criteria,
                originally_willing=originally_willing,
                pain_resolved=pain_resolved,
            )
        )
    return tuple(
        sorted(projected, key=lambda item: (item.candidate_id, item.refusal_id))
    )


def route_refusal_history(
    before: MatchingCriteriaSnapshot,
    after: MatchingCriteriaSnapshot,
    history: Sequence[RefusalHistoryEntry],
) -> tuple[RefusalRouting, ...]:
    """Route every refusal exactly once for one criteria transition.

    The source must explicitly mark original willingness or a resolved pain.
    Unmarked refusals are deliberately silent-excluded (G3), preventing the
    coordinator from inventing consent from a changed criteria payload.
    """

    changed_keys = {
        key for key in set(before.criteria) | set(after.criteria)
        if before.criteria.get(key) != after.criteria.get(key)
    }
    diff_fingerprint = fingerprint_payload({
        "before": before.fingerprint.value,
        "after": after.fingerprint.value,
        "changed": tuple(sorted(changed_keys)),
    })
    result: list[RefusalRouting] = []
    for entry in history:
        if not isinstance(entry, RefusalHistoryEntry):
            raise TypeError("refusal history must contain typed entries")
        if entry.originally_willing and entry.pain_resolved:
            raise MatchingDomainError(MatchingDomainErrorCode.INVALID, "refusal routing flags must be mutually exclusive")
        intersects_changed = bool(set(entry.affected_criteria) & changed_keys)
        if intersects_changed and entry.originally_willing:
            group = RefusalRoutingGroup.GROUP1_ORIGINAL_WILLING_RECONFIRM
            action = "reconfirm"
        elif intersects_changed and entry.pain_resolved:
            group = RefusalRoutingGroup.GROUP2_PAIN_RESOLVED_REPROBE
            action = "reprobe"
        else:
            group = RefusalRoutingGroup.GROUP3_UNRELATED_SILENT_EXCLUDE
            action = "silent_exclude"
        result.append(RefusalRouting(entry.candidate_id, entry.refusal_id, group, action, entry.reason_code, entry.snapshot_id, diff_fingerprint))
    return tuple(sorted(result, key=lambda item: (item.candidate_id, item.refusal_id)))


def build_willingness_lineage(
    *,
    event_id: str,
    candidate_id: str,
    staff_id: int,
    snapshot: MatchingCriteriaSnapshot,
    previous_state: str,
    current_state: str,
    reason_code: str | None = None,
    affected_criteria: Sequence[str] = (),
) -> DynamicWillingnessLineage:
    return DynamicWillingnessLineage(event_id, candidate_id, staff_id, snapshot.snapshot_id, snapshot.source_versions, previous_state, current_state, reason_code, tuple(affected_criteria))


def build_zero_candidate_decision(
    *,
    event_id: str,
    case_no: str,
    alternative: ZeroCandidateAlternative,
    decision: ZeroCandidateDecision | str,
    actor_id: str,
    source_versions: MatchingSourceTuple,
    assignment_request_id: str | None = None,
) -> ZeroCandidateDecisionLineage:
    normalized = ZeroCandidateDecision(decision)
    outcome = "alternative_agreed_pending_owning_workflows" if normalized is ZeroCandidateDecision.AGREE else "awaiting_matching"
    if normalized is ZeroCandidateDecision.DISAGREE and assignment_request_id is not None:
        raise MatchingDomainError(MatchingDomainErrorCode.CUSTOMER_ACCEPTANCE_NOT_CONVERSION, "disagree cannot create assignment request")
    return ZeroCandidateDecisionLineage(event_id, case_no, alternative.alternative_id, alternative.policy_id, alternative.policy_version, normalized, outcome, actor_id, source_versions, assignment_request_id)


def build_cross_domain_request(
    *,
    request_id: str,
    request_kind: MatchingRequestKind | str,
    case_no: str,
    package: MatchingPackage,
    criteria_snapshot_id: str,
    candidate_id: str | None,
    source_versions: MatchingSourceTuple,
    lineage_event_id: str,
    reason: str,
) -> MatchingCrossDomainRequest:
    """Create a typed request for the owning Assignment/Scheduling workflow."""

    if package.criteria_snapshot_id != criteria_snapshot_id:
        raise MatchingDomainError(MatchingDomainErrorCode.SOURCE_CONFLICT, "cross-domain request snapshot is stale")
    return MatchingCrossDomainRequest(request_id, MatchingRequestKind(request_kind), case_no, package.package_id, package.version, criteria_snapshot_id, candidate_id, source_versions, lineage_event_id, reason)


def build_zero_candidate_alternative(
    *,
    alternative_id: str,
    policy_id: str,
    policy_version: int,
    relaxed_criteria: Sequence[str],
    unchanged_hard_criteria: Sequence[str],
    candidate_result: MatchingCandidateResult | None = None,
    risk_warnings: Sequence[str] = (),
    deterministic_rank: int = 1,
) -> ZeroCandidateAlternative:
    relaxed = tuple(sorted(set(relaxed_criteria)))
    hard = tuple(sorted(set(unchanged_hard_criteria)))
    preview_fingerprint = fingerprint_payload({"alternative_id": alternative_id, "hard": hard, "policy": policy_id, "policy_version": policy_version, "relaxed": relaxed, "candidate_id": candidate_result.candidate_id if candidate_result else None})
    return ZeroCandidateAlternative(alternative_id, policy_id, policy_version, relaxed, hard, candidate_result, tuple(risk_warnings), deterministic_rank, preview_fingerprint)


def build_manual_matching_package(
    *,
    package_id: str,
    version: int,
    segments: Sequence[MatchingSegment],
    required_service_dates: Sequence[date],
    candidate_results: Sequence[MatchingCandidateResult],
    criteria_snapshot_id: str,
    source_versions: MatchingSourceTuple,
) -> MatchingPackage:
    """Validate an administrator-selected package without ranking candidates."""

    selected_segments = tuple(segments)
    candidates = tuple(
        sorted(
            candidate_results,
            key=lambda item: (
                not bool(item.staff_name),
                item.staff_name.casefold(),
                item.staff_id,
                item.candidate_id,
            ),
        )
    )
    candidates_by_staff: dict[int, MatchingCandidateResult] = {}
    for candidate in candidates:
        if candidate.staff_id in candidates_by_staff:
            raise MatchingDomainError(
                MatchingDomainErrorCode.INVALID,
                "candidate staff identity must be unique",
            )
        candidates_by_staff[candidate.staff_id] = candidate
    for segment in selected_segments:
        candidate = candidates_by_staff.get(segment.staff_id)
        if candidate is None:
            raise MatchingDomainError(
                MatchingDomainErrorCode.CANDIDATE_NOT_FOUND,
                "selected staff is not in the current candidate pool",
            )
        if (
            candidate.eligibility is not CandidateEligibility.ELIGIBLE
            or candidate.willingness != WillingnessState.WILLING.value
        ):
            raise MatchingDomainError(
                MatchingDomainErrorCode.WILLINGNESS_CONFLICT,
                "selected staff must be eligible and willing",
            )
        if not set(segment.service_dates).issubset(candidate.coverage_evidence):
            raise MatchingDomainError(
                MatchingDomainErrorCode.COVERAGE_INCOMPLETE,
                "selected staff does not cover the segment service dates",
            )
    mode = MatchingPackageMode.SINGLE if len(selected_segments) == 1 else MatchingPackageMode.MULTI_SEGMENT
    return MatchingPackage(
        package_id=package_id,
        version=version,
        mode=mode,
        segments=selected_segments,
        required_service_dates=tuple(required_service_dates),
        candidate_results=candidates,
        criteria_snapshot_id=criteria_snapshot_id,
        source_versions=source_versions,
    )


def _validate_package_coverage(package: MatchingPackage) -> None:
    if package.mode is MatchingPackageMode.SINGLE and len(package.segments) != 1:
        raise MatchingDomainError(MatchingDomainErrorCode.COVERAGE_INCOMPLETE, "single package requires one segment")
    if package.mode is MatchingPackageMode.MULTI_SEGMENT and not 2 <= len(package.segments) <= 4:
        raise MatchingDomainError(MatchingDomainErrorCode.COVERAGE_INCOMPLETE, "multi package requires two to four segments")
    ordered = tuple(sorted(package.segments, key=lambda item: item.sequence))
    if ordered != package.segments or tuple(item.sequence for item in ordered) != tuple(range(1, len(ordered) + 1)):
        raise MatchingDomainError(MatchingDomainErrorCode.COVERAGE_INCOMPLETE, "package segments must be ordered")
    covered = tuple(day for item in ordered for day in item.service_dates)
    if covered != package.required_service_dates:
        raise MatchingDomainError(MatchingDomainErrorCode.COVERAGE_INCOMPLETE, "package does not conserve service dates")


def _candidate_payload(candidate: MatchingCandidateResult) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "coverage_evidence": tuple(
            item.isoformat() for item in candidate.coverage_evidence
        ),
        "criteria_results": tuple(
            {
                "code": item.code,
                "detail": item.detail,
                "source_version": item.source_version.as_payload(),
                "status": item.status.value,
            }
            for item in candidate.criteria_results
        ),
        "eligibility": candidate.eligibility.value,
        "notification_lineage": candidate.notification_lineage,
        "rejection_reasons": candidate.rejection_reasons,
        "staff_id": candidate.staff_id,
        "staff_name": candidate.staff_name,
        "willingness": candidate.willingness,
    }


def _validate_identity(value: str, field_name: str, maximum: int = _MAXIMUM_IDENTITY_LENGTH) -> None:
    require_canonical_text(value, field_name, maximum)


def _validate_tuple(value: object, item_type: type, field_name: str) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise TypeError(f"{field_name} must be a typed tuple")


def _validate_text_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, str) or not item for item in value):
        raise TypeError(f"{field_name} must be a tuple of text")
    if value != tuple(sorted(set(value))):
        raise ValueError(f"{field_name} must be sorted and unique")


def _validate_reason_codes(value: tuple[str, ...]) -> None:
    _validate_text_tuple(value, "reason codes")


def _normalize_stable_reason_codes(value: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    """Validate and serialize only the closed rejection-reason vocabulary."""

    _validate_text_tuple(value, field_name)
    try:
        return tuple(StableRejectionReason(item).value for item in value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use stable rejection reason codes") from exc


def _normalize_stable_reason_code(value: str, field_name: str) -> str:
    """Validate one refusal reason without widening other free-form fields."""

    _validate_identity(value, field_name)
    try:
        return StableRejectionReason(value).value
    except ValueError as exc:
        raise ValueError(f"{field_name} must use a stable rejection reason code") from exc


def _validate_dates(value: object, field_name: str) -> None:
    if not isinstance(value, tuple) or any(type(item) is not date for item in value):
        raise TypeError(f"{field_name} must contain calendar dates")
    if value != tuple(sorted(set(value))):
        raise ValueError(f"{field_name} must be sorted and unique")


def _freeze_value(value: Any) -> Any:
    """Deep-freeze JSON-like criteria so a snapshot cannot mutate through nesting."""

    if value is None or isinstance(value, (str, bool, int)) and not isinstance(value, bool):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    raise TypeError("criteria contains a non-canonical value")


__all__ = [
    "CandidateEligibility",
    "CriterionStatus",
    "StableRejectionReason",
    "MatchingCandidateResult",
    "MatchingCriteriaDiff",
    "MatchingCriteriaResult",
    "MatchingCriteriaSnapshot",
    "MatchingCrossDomainRequest",
    "MatchingDecisionLineage",
    "MatchingDomainError",
    "MatchingDomainErrorCode",
    "MatchingPackage",
    "MatchingPackageMode",
    "MatchingPackageState",
    "MatchingSegment",
    "MatchingSourceTuple",
    "MatchingSourceVersion",
    "MatchingRefusalHistory",
    "MatchingRefusalRoute",
    "RefusalHistoryEntry",
    "RefusalRouting",
    "RefusalRoutingGroup",
    "DynamicWillingnessLineage",
    "WillingnessState",
    "ZeroCandidateDecision",
    "ZeroCandidateDecisionLineage",
    "MatchingRequestKind",
    "AssignmentConversionRequest",
    "RematchRequest",
    "SOURCE_KINDS",
    "ZeroCandidateAlternative",
    "build_criteria_diff",
    "build_criteria_snapshot",
    "build_cross_domain_request",
    "build_willingness_lineage",
    "build_zero_candidate_decision",
    "build_zero_candidate_alternative",
    "canonical_source_tuple",
    "route_refusal_history",
]

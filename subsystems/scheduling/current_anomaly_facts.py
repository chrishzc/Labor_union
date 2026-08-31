"""Scheduling-owned zero-write facts for the three current anomaly predicates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.validation import require_canonical_text, require_nonnegative_integer, require_positive_integer

SCHEDULING_ANOMALY_OWNER_DOMAIN = "scheduling"
SCHEDULING_ANOMALY_OWNER_ROOT_TYPE = "scheduling_current_fact"


class SchedulingCurrentIssueCode(StrEnum):
    REPLACEMENT_INCOMPLETE = "SCHEDULE-002"
    ASSIGNMENT_OVERLAP = "SCHEDULE-003"
    COVERAGE_INVALID = "SCHEDULE-006"


class SchedulingCurrentFactReason(StrEnum):
    REPLACEMENT_SUCCESSOR_MISSING = "replacement_successor_missing"
    DAILY_OUTCOME_INCOMPLETE = "daily_outcome_incomplete"
    SERVICE_OWNERSHIP_INCOMPLETE = "service_ownership_incomplete"
    PAYROLL_IMPACT_INCOMPLETE = "payroll_impact_incomplete"
    FINANCE_IMPACT_INCOMPLETE = "finance_impact_incomplete"
    STAFF_OCCUPANCY_CONFLICT = "staff_occupancy_conflict"
    OFFICIAL_SERVICE_DATES_INVALID = "official_service_dates_invalid"
    COVERAGE_INCOMPLETE = "coverage_incomplete"
    HOURS_MISMATCH = "hours_mismatch"
    GENERATION_CONFLICT = "generation_conflict"
    OWNER_READBACK_INCOMPLETE = "owner_readback_incomplete"


@dataclass(frozen=True, slots=True)
class SchedulingReplacementCurrentFact:
    assignment_id: int
    owner_snapshot_token: str
    owner_version: int
    authoritative_complete: bool
    exact_successor: bool
    daily_outcomes_complete: bool
    service_ownership_complete: bool
    payroll_impact_complete: bool
    finance_impact_complete: bool

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        _validate_common(self.owner_snapshot_token, self.owner_version, self.authoritative_complete)
        _validate_flags(self.exact_successor, self.daily_outcomes_complete, self.service_ownership_complete, self.payroll_impact_complete, self.finance_impact_complete)

    @property
    def unresolved_reason_codes(self) -> tuple[SchedulingCurrentFactReason, ...]:
        reasons = []
        if not self.authoritative_complete:
            reasons.append(SchedulingCurrentFactReason.OWNER_READBACK_INCOMPLETE)
        for complete, reason in (
            (self.exact_successor, SchedulingCurrentFactReason.REPLACEMENT_SUCCESSOR_MISSING),
            (self.daily_outcomes_complete, SchedulingCurrentFactReason.DAILY_OUTCOME_INCOMPLETE),
            (self.service_ownership_complete, SchedulingCurrentFactReason.SERVICE_OWNERSHIP_INCOMPLETE),
            (self.payroll_impact_complete, SchedulingCurrentFactReason.PAYROLL_IMPACT_INCOMPLETE),
            (self.finance_impact_complete, SchedulingCurrentFactReason.FINANCE_IMPACT_INCOMPLETE),
        ):
            if not complete:
                reasons.append(reason)
        return tuple(reasons)

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


@dataclass(frozen=True, slots=True)
class SchedulingOverlapCurrentFact:
    assignment_id_a: int
    assignment_id_b: int
    owner_snapshot_token: str
    owner_version: int
    authoritative_complete: bool
    current_effective_overlap: bool

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id_a, "first assignment id")
        require_positive_integer(self.assignment_id_b, "second assignment id")
        if self.assignment_id_a >= self.assignment_id_b:
            raise ValueError("assignment overlap identity is not canonical")
        _validate_common(self.owner_snapshot_token, self.owner_version, self.authoritative_complete)
        _validate_flags(self.current_effective_overlap)

    @property
    def unresolved_reason_codes(self) -> tuple[SchedulingCurrentFactReason, ...]:
        if not self.authoritative_complete:
            return (SchedulingCurrentFactReason.OWNER_READBACK_INCOMPLETE,)
        if self.current_effective_overlap:
            return (SchedulingCurrentFactReason.STAFF_OCCUPANCY_CONFLICT,)
        return ()

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


@dataclass(frozen=True, slots=True)
class SchedulingCoverageCurrentFact:
    case_no: str
    generation: int
    owner_snapshot_token: str
    owner_version: int
    authoritative_complete: bool
    official_service_dates_valid: bool
    service_ownership_valid: bool
    coverage_valid: bool
    hours_valid: bool
    staff_occupancy_valid: bool
    generation_valid: bool

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.generation, "generation")
        _validate_common(self.owner_snapshot_token, self.owner_version, self.authoritative_complete)
        _validate_flags(self.official_service_dates_valid, self.service_ownership_valid, self.coverage_valid, self.hours_valid, self.staff_occupancy_valid, self.generation_valid)

    @property
    def unresolved_reason_codes(self) -> tuple[SchedulingCurrentFactReason, ...]:
        reasons = []
        if not self.authoritative_complete:
            reasons.append(SchedulingCurrentFactReason.OWNER_READBACK_INCOMPLETE)
        for valid, reason in (
            (self.official_service_dates_valid, SchedulingCurrentFactReason.OFFICIAL_SERVICE_DATES_INVALID),
            (self.service_ownership_valid, SchedulingCurrentFactReason.SERVICE_OWNERSHIP_INCOMPLETE),
            (self.coverage_valid, SchedulingCurrentFactReason.COVERAGE_INCOMPLETE),
            (self.hours_valid, SchedulingCurrentFactReason.HOURS_MISMATCH),
            (self.staff_occupancy_valid, SchedulingCurrentFactReason.STAFF_OCCUPANCY_CONFLICT),
            (self.generation_valid, SchedulingCurrentFactReason.GENERATION_CONFLICT),
        ):
            if not valid:
                reasons.append(reason)
        return tuple(reasons)

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


SchedulingCurrentFact = SchedulingReplacementCurrentFact | SchedulingOverlapCurrentFact | SchedulingCoverageCurrentFact


@dataclass(frozen=True, slots=True)
class SchedulingAnomalyRecheckRequest:
    definition_code: SchedulingCurrentIssueCode
    subject_ids: tuple[str, ...]
    owner_root_ids: tuple[str, ...]
    owner_version: int
    owner_snapshot_token: str
    intent_identity: str

    def __post_init__(self) -> None:
        if not self.subject_ids or tuple(sorted(set(self.subject_ids))) != self.subject_ids:
            raise ValueError("scheduling recheck subject ids must be sorted and unique")
        if not self.owner_root_ids or tuple(sorted(set(self.owner_root_ids))) != self.owner_root_ids:
            raise ValueError("scheduling recheck owner root ids must be sorted and unique")
        for value in self.subject_ids:
            require_canonical_text(value, "recheck subject id", 191)
        for value in self.owner_root_ids:
            require_canonical_text(value, "recheck owner root id", 191)
        require_nonnegative_integer(self.owner_version, "owner version")
        require_canonical_text(self.owner_snapshot_token, "owner snapshot token", 191)
        require_canonical_text(self.intent_identity, "recheck intent identity", 191)


@dataclass(frozen=True, slots=True)
class SchedulingOverlapRecheckRequest:
    affected_assignment_ids: tuple[int, ...]
    affected_staff_ids: tuple[int, ...]
    owner_version: int
    owner_snapshot_token: str
    intent_identity: str

    def __post_init__(self) -> None:
        for values, field in (
            (self.affected_assignment_ids, "affected assignment ids"),
            (self.affected_staff_ids, "affected staff ids"),
        ):
            if values != tuple(sorted(set(values))) or any(type(value) is not int or value <= 0 for value in values):
                raise ValueError(field + " must be sorted unique positive integers")
        if not self.affected_assignment_ids and not self.affected_staff_ids:
            raise ValueError("scheduling overlap recheck requires an affected root")
        require_nonnegative_integer(self.owner_version, "owner version")
        require_canonical_text(self.owner_snapshot_token, "owner snapshot token", 191)
        require_canonical_text(self.intent_identity, "recheck intent identity", 191)


def build_scheduling_recheck_request(
    fact: SchedulingCurrentFact,
    intent_identity: str,
) -> SchedulingAnomalyRecheckRequest:
    require_canonical_text(intent_identity, "recheck intent identity", 191)
    code, subject_ids, root_ids = _scope_values(fact)
    return SchedulingAnomalyRecheckRequest(
        code,
        subject_ids,
        tuple(sorted(root_ids)),
        fact.owner_version,
        fact.owner_snapshot_token,
        intent_identity,
    )


def build_scheduling_coverage_recheck_request(
    case_no: str,
    generation: int,
    owner_version: int,
    intent_identity: str,
) -> SchedulingAnomalyRecheckRequest:
    """Build the exact SCHEDULE-006 recheck after an owner generation commit."""

    require_canonical_text(case_no, "case number", 50)
    require_positive_integer(generation, "generation")
    require_nonnegative_integer(owner_version, "owner version")
    require_canonical_text(intent_identity, "recheck intent identity", 191)
    subject_id = case_no + ":" + str(generation)
    return SchedulingAnomalyRecheckRequest(
        SchedulingCurrentIssueCode.COVERAGE_INVALID,
        (subject_id,),
        ("case:" + case_no,),
        owner_version,
        "generation:" + str(generation),
        intent_identity,
    )


def build_scheduling_replacement_recheck_request(
    assignment_id: int,
    owner_version: int,
    owner_snapshot_token: str,
    intent_identity: str,
) -> SchedulingAnomalyRecheckRequest:
    require_positive_integer(assignment_id, "assignment id")
    value = str(assignment_id)
    return SchedulingAnomalyRecheckRequest(
        SchedulingCurrentIssueCode.REPLACEMENT_INCOMPLETE,
        (value,),
        ("assignment:" + value,),
        owner_version,
        owner_snapshot_token,
        intent_identity,
    )


def _scope_values(fact: SchedulingCurrentFact):
    if isinstance(fact, SchedulingReplacementCurrentFact):
        value = str(fact.assignment_id)
        return SchedulingCurrentIssueCode.REPLACEMENT_INCOMPLETE, (value,), ("assignment:" + value,)
    if isinstance(fact, SchedulingOverlapCurrentFact):
        left, right = str(fact.assignment_id_a), str(fact.assignment_id_b)
        return SchedulingCurrentIssueCode.ASSIGNMENT_OVERLAP, (left + ":" + right,), ("assignment:" + left, "assignment:" + right)
    value = fact.case_no + ":" + str(fact.generation)
    return SchedulingCurrentIssueCode.COVERAGE_INVALID, (value,), ("case:" + fact.case_no,)


def _validate_common(snapshot_token: str, owner_version: int, complete: bool) -> None:
    require_canonical_text(snapshot_token, "owner snapshot token", 191)
    require_nonnegative_integer(owner_version, "owner version")
    _validate_flags(complete)


def _validate_flags(*values: bool) -> None:
    if any(type(value) is not bool for value in values):
        raise TypeError("scheduling current-fact flags must be bool")


__all__ = [
    "SCHEDULING_ANOMALY_OWNER_DOMAIN", "SCHEDULING_ANOMALY_OWNER_ROOT_TYPE",
    "SchedulingAnomalyRecheckRequest", "SchedulingCoverageCurrentFact", "SchedulingCurrentFact", "SchedulingCurrentFactReason",
    "SchedulingCurrentIssueCode", "SchedulingOverlapCurrentFact", "SchedulingReplacementCurrentFact",
    "SchedulingOverlapRecheckRequest",
    "build_scheduling_coverage_recheck_request", "build_scheduling_recheck_request",
    "build_scheduling_replacement_recheck_request",
]

"""
File: service_before_replacement.py
Description: 服務前換人 successor 的 Scheduling-owned pure domain contract。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Iterable

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

_CASE_MAX = 50
_IDENTITY_MAX = 191
_REASON_MAX = 500


class ServiceBeforeReplacementError(ValueError):
    """A replacement snapshot cannot satisfy a Scheduling owner invariant."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReplacementScenario(StrEnum):
    R01 = "R-01"
    R02 = "R-02"
    R03 = "R-03"
    R04 = "R-04"
    R07 = "R-07"


class ReplacementOutcome(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    SUBSTITUTION_REFERRAL = "substitution_referral"


class ReplacementResumeStep(StrEnum):
    STEP_2 = "step_2"
    STEP_3 = "step_3"
    STEP_4 = "step_4"


class ReplacementProjectionKind(StrEnum):
    SUCCESSOR_MATCHING = "successor_matching"
    MATCHING_ONLY_ZERO_SERVICE = "matching_only_zero_service"


class ReplacementRootKind(StrEnum):
    CANDIDATE_BINDING = "candidate_binding"
    WILLINGNESS = "willingness"
    MATCHING_PLAN = "matching_plan"
    MATCHING_SEGMENT = "matching_segment"
    MATCHING_REPLY = "matching_reply"
    RECIPIENT_CONFIRMATION = "recipient_confirmation"
    WAITING_LOCK = "waiting_lock"
    COMMITMENT = "commitment"
    SIGNBACK = "signback"
    RECIPIENT_BINDING = "recipient_binding"
    EFFECTIVE_GENERATION = "effective_generation"
    ASSIGNMENT = "assignment"
    OFFICIAL_SCHEDULE = "official_schedule"
    SUCCESSOR_ROUND = "successor_round"


_IMPACTED_KINDS: dict[ReplacementScenario, tuple[ReplacementRootKind, ...]] = {
    ReplacementScenario.R01: (ReplacementRootKind.CANDIDATE_BINDING, ReplacementRootKind.WILLINGNESS),
    ReplacementScenario.R02: (ReplacementRootKind.MATCHING_PLAN, ReplacementRootKind.MATCHING_SEGMENT, ReplacementRootKind.MATCHING_REPLY, ReplacementRootKind.RECIPIENT_CONFIRMATION),
    ReplacementScenario.R03: (ReplacementRootKind.WAITING_LOCK, ReplacementRootKind.COMMITMENT, ReplacementRootKind.SIGNBACK, ReplacementRootKind.RECIPIENT_BINDING),
    ReplacementScenario.R04: (ReplacementRootKind.EFFECTIVE_GENERATION, ReplacementRootKind.ASSIGNMENT, ReplacementRootKind.OFFICIAL_SCHEDULE),
    ReplacementScenario.R07: (ReplacementRootKind.SUCCESSOR_ROUND,),
}


@dataclass(frozen=True, slots=True)
class ReplacementReasonEvidence:
    reason: str
    evidence_references: tuple[str, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "replacement reason", _REASON_MAX)
        _validate_text_tuple(self.evidence_references, "replacement evidence reference", _IDENTITY_MAX)

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (self.reason, self.evidence_references)


@dataclass(frozen=True, slots=True)
class AuthoritativeActualServiceProof:
    """Typed official-service fact used by the hard replacement gate."""

    case_no: str
    service_dates: tuple[date, ...]
    source_identity: str
    source_version: int
    fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "actual service proof case number", _CASE_MAX)
        _validate_dates(self.service_dates, "actual service proof service dates")
        require_canonical_text(self.source_identity, "actual service proof source identity", _IDENTITY_MAX)
        require_nonnegative_integer(self.source_version, "actual service proof source version")
        expected = fingerprint_payload({
            "kind": "authoritative-actual-service-proof",
            "case_no": self.case_no,
            "service_dates": tuple(item.isoformat() for item in self.service_dates),
            "source_identity": self.source_identity,
            "source_version": self.source_version,
        })
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif not isinstance(self.fingerprint, PreviewFingerprint):
            raise TypeError("actual service proof fingerprint is invalid")
        elif self.fingerprint != expected:
            raise ServiceBeforeReplacementError("actual_service_proof_fingerprint_mismatch")

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (self.case_no, tuple(item.isoformat() for item in self.service_dates), self.source_identity, self.source_version, self.fingerprint.value)


ActualServiceProof = AuthoritativeActualServiceProof
OfficialServiceProof = AuthoritativeActualServiceProof


@dataclass(frozen=True, slots=True)
class ReplacementRootIdentity:
    """An immutable Scheduling root identity; status is never edited in place."""

    kind: ReplacementRootKind | str
    root_id: str
    case_no: str
    current: bool = True
    caregiver_bound: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ReplacementRootKind):
            try:
                object.__setattr__(self, "kind", ReplacementRootKind(self.kind))
            except ValueError as error:
                raise ServiceBeforeReplacementError("replacement_root_kind_invalid") from error
        require_canonical_text(self.root_id, "replacement root id", _IDENTITY_MAX)
        require_canonical_text(self.case_no, "replacement root case number", _CASE_MAX)
        if not isinstance(self.current, bool) or not isinstance(self.caregiver_bound, bool):
            raise TypeError("replacement root flags must be bool")

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (self.kind.value, self.root_id, self.case_no, self.current, self.caregiver_bound)


@dataclass(frozen=True, slots=True)
class ReplacementRootDelta:
    retained: tuple[ReplacementRootIdentity, ...]
    superseded: tuple[ReplacementRootIdentity, ...]
    created: tuple[ReplacementRootIdentity, ...]

    def __post_init__(self) -> None:
        for roots, label in ((self.retained, "retained roots"), (self.superseded, "superseded roots"), (self.created, "created roots")):
            _validate_roots(roots, None, label)
        sets = tuple({root.root_id for root in roots} for roots in (self.retained, self.superseded, self.created))
        if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
            raise ServiceBeforeReplacementError("replacement_root_delta_identity_overlap")

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return tuple(tuple(root.canonical_tuple for root in roots) for roots in (self.retained, self.superseded, self.created))


@dataclass(frozen=True, slots=True)
class SuccessorRoundFact:
    """An already persisted successor round that R-07 may reuse."""

    case_no: str
    round_identity: str
    generation_identity: str
    event_identity: str
    generation_version: int
    event_version: int
    candidate_count: int
    zero_candidate_disposition: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "successor round case number", _CASE_MAX)
        for value, name in ((self.round_identity, "successor round identity"), (self.generation_identity, "successor round generation identity"), (self.event_identity, "successor round event identity")):
            require_canonical_text(value, name, _IDENTITY_MAX)
        require_nonnegative_integer(self.generation_version, "successor round generation version")
        require_nonnegative_integer(self.event_version, "successor round event version")
        require_nonnegative_integer(self.candidate_count, "successor round candidate count")
        if self.candidate_count == 0:
            require_canonical_text(self.zero_candidate_disposition, "zero candidate disposition", _REASON_MAX)
        elif self.zero_candidate_disposition is not None:
            raise ServiceBeforeReplacementError("successor_round_zero_candidate_disposition_invalid")

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (self.case_no, self.round_identity, self.generation_identity, self.event_identity, self.generation_version, self.event_version, self.candidate_count, self.zero_candidate_disposition)


ExistingSuccessorRound = SuccessorRoundFact


@dataclass(frozen=True, slots=True)
class MatchingZeroCandidateProof:
    """Current Matching-owned no-candidate package/event consumed by R-07."""

    case_no: str
    package_identity: str
    package_version: int
    criteria_snapshot_identity: str
    event_identity: str
    event_version: int
    package_fingerprint: PreviewFingerprint
    event_fingerprint: PreviewFingerprint
    receipt_identity: str
    assignment_intent_identity: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "zero candidate proof case number", _CASE_MAX)
        require_canonical_text(self.package_identity, "zero candidate package identity", _IDENTITY_MAX)
        require_canonical_text(self.criteria_snapshot_identity, "zero candidate criteria identity", _IDENTITY_MAX)
        require_canonical_text(self.event_identity, "zero candidate event identity", _IDENTITY_MAX)
        require_canonical_text(self.receipt_identity, "zero candidate receipt identity", _IDENTITY_MAX)
        require_canonical_text(self.assignment_intent_identity, "zero candidate assignment intent identity", _IDENTITY_MAX)
        require_nonnegative_integer(self.package_version, "zero candidate package version")
        require_nonnegative_integer(self.event_version, "zero candidate event version")
        if not isinstance(self.package_fingerprint, PreviewFingerprint) or not isinstance(
            self.event_fingerprint, PreviewFingerprint
        ):
            raise TypeError("zero candidate fingerprint is invalid")
        if self.event_version != self.package_version:
            raise ServiceBeforeReplacementError("zero_candidate_owner_version_drift")

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (
            self.case_no,
            self.package_identity,
            self.package_version,
            self.criteria_snapshot_identity,
            self.event_identity,
            self.event_version,
            self.package_fingerprint.value,
            self.event_fingerprint.value,
            self.receipt_identity,
            self.assignment_intent_identity,
        )


@dataclass(frozen=True, slots=True)
class CandidatePoolReuseProof:
    """Fresh candidate-pool evidence bound to case, successor, versions and identity."""

    pool_identity: str
    round_identity: str
    coverage_version: int
    availability_version: int
    willingness_version: int
    fingerprint: PreviewFingerprint
    same_round: bool = True
    coverage_valid: bool = True
    availability_valid: bool = True
    willingness_valid: bool = True
    fresh: bool = True
    accepted_candidate: bool = False
    case_no: str | None = None
    successor_round_identity: str | None = None
    generation_version: int | None = None
    event_version: int | None = None
    candidate_identity: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.pool_identity, "candidate pool identity", _IDENTITY_MAX)
        require_canonical_text(self.round_identity, "candidate pool round identity", _IDENTITY_MAX)
        for value, name in ((self.coverage_version, "candidate coverage version"), (self.availability_version, "candidate availability version"), (self.willingness_version, "candidate willingness version")):
            require_nonnegative_integer(value, name)
        if not isinstance(self.fingerprint, PreviewFingerprint):
            raise TypeError("candidate pool fingerprint is invalid")
        for value in (self.same_round, self.coverage_valid, self.availability_valid, self.willingness_valid, self.fresh, self.accepted_candidate):
            if not isinstance(value, bool):
                raise TypeError("candidate pool proof flags must be bool")
        if self.case_no is not None:
            require_canonical_text(self.case_no, "candidate pool proof case number", _CASE_MAX)
        if self.successor_round_identity is not None:
            require_canonical_text(self.successor_round_identity, "candidate pool successor round identity", _IDENTITY_MAX)
        if self.candidate_identity is not None:
            require_canonical_text(self.candidate_identity, "candidate identity", _IDENTITY_MAX)
        for value, name in ((self.generation_version, "candidate proof generation version"), (self.event_version, "candidate proof event version")):
            if value is not None:
                require_nonnegative_integer(value, name)

    @property
    def reusable(self) -> bool:
        return all((self.same_round, self.coverage_valid, self.availability_valid, self.willingness_valid, self.fresh, self.case_no is not None, self.successor_round_identity is not None, self.generation_version is not None, self.event_version is not None, self.candidate_identity is not None))

    def bound_to(self, facts: "ServiceBeforeReplacementFacts") -> bool:
        expected_round = facts.candidate_pool_round_identity or facts.successor_round_identity
        return self.reusable and self.round_identity == self.successor_round_identity and self.case_no == facts.case_no and self.successor_round_identity == expected_round and self.generation_version == facts.generation_version and self.event_version == facts.event_version and (facts.candidate_identity is None or self.candidate_identity == facts.candidate_identity)

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (self.pool_identity, self.round_identity, self.coverage_version, self.availability_version, self.willingness_version, self.fingerprint.value, self.same_round, self.coverage_valid, self.availability_valid, self.willingness_valid, self.fresh, self.accepted_candidate, self.case_no, self.successor_round_identity, self.generation_version, self.event_version, self.candidate_identity)


@dataclass(frozen=True, slots=True)
class ServiceBeforeReplacementFacts:
    case_no: str
    scenario: ReplacementScenario | str
    actual_service_dates: tuple[date, ...]
    prior_generation_identity: str
    prior_event_identity: str
    generation_version: int
    event_version: int
    current_roots: tuple[ReplacementRootIdentity, ...]
    retained_history: tuple[ReplacementRootIdentity, ...] = ()
    candidate_pool_reuse: CandidatePoolReuseProof | None = None
    actual_service_proof_available: bool = False
    actual_service_proof: AuthoritativeActualServiceProof | None = None
    aggregate_version: int | None = None
    prior_aggregate_identity: str | None = None
    prior_case_no: str | None = None
    replacement_reason: str = "service_before_replacement"
    reason_evidence: tuple[str, ...] = ()
    successor_round: SuccessorRoundFact | None = None
    candidate_pool_round_identity: str | None = None
    candidate_identity: str | None = None
    matching_zero_candidate_proof: MatchingZeroCandidateProof | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "replacement case number", _CASE_MAX)
        if not isinstance(self.scenario, ReplacementScenario):
            try:
                object.__setattr__(self, "scenario", ReplacementScenario(self.scenario))
            except ValueError as error:
                raise ServiceBeforeReplacementError("replacement_scenario_invalid") from error
        _validate_dates(self.actual_service_dates, "actual service dates")
        for value, name in ((self.prior_generation_identity, "prior generation identity"), (self.prior_event_identity, "prior event identity")):
            require_canonical_text(value, name, _IDENTITY_MAX)
        require_nonnegative_integer(self.generation_version, "replacement generation version")
        require_nonnegative_integer(self.event_version, "replacement event version")
        _validate_roots(self.current_roots, self.case_no, "current replacement roots")
        _validate_roots(self.retained_history, self.case_no, "retained replacement roots")
        if {item.root_id for item in self.current_roots} & {item.root_id for item in self.retained_history}:
            raise ServiceBeforeReplacementError("replacement_root_cross_set_identity")
        if self.candidate_pool_reuse is not None and not isinstance(self.candidate_pool_reuse, CandidatePoolReuseProof):
            raise TypeError("candidate pool reuse proof is invalid")
        if not isinstance(self.actual_service_proof_available, bool):
            raise TypeError("actual service proof availability must be bool")
        if self.actual_service_proof is not None:
            if not isinstance(self.actual_service_proof, AuthoritativeActualServiceProof):
                raise TypeError("actual service proof is invalid")
            if self.actual_service_proof.case_no != self.case_no or self.actual_service_proof.service_dates != self.actual_service_dates:
                raise ServiceBeforeReplacementError("actual_service_proof_case_or_dates_mismatch")
            if not self.actual_service_proof_available:
                object.__setattr__(self, "actual_service_proof_available", True)
        if self.aggregate_version is None:
            object.__setattr__(self, "aggregate_version", self.generation_version)
        require_nonnegative_integer(self.aggregate_version, "replacement aggregate version")
        if self.prior_aggregate_identity is None:
            object.__setattr__(self, "prior_aggregate_identity", f"aggregate:{self.case_no}:{self.aggregate_version}")
        require_canonical_text(self.prior_aggregate_identity, "prior aggregate identity", _IDENTITY_MAX)
        if self.prior_case_no is None:
            object.__setattr__(self, "prior_case_no", self.case_no)
        require_canonical_text(self.prior_case_no, "prior case number", _CASE_MAX)
        if self.prior_case_no != self.case_no:
            raise ServiceBeforeReplacementError("replacement_prior_case_mismatch")
        require_canonical_text(self.replacement_reason, "replacement reason", _REASON_MAX)
        _validate_text_tuple(self.reason_evidence, "replacement evidence reference", _IDENTITY_MAX)
        if self.successor_round is not None:
            if not isinstance(self.successor_round, SuccessorRoundFact):
                raise TypeError("successor round fact is invalid")
            if self.successor_round.case_no != self.case_no:
                raise ServiceBeforeReplacementError("successor_round_case_mismatch")
        if self.candidate_pool_round_identity is not None:
            require_canonical_text(self.candidate_pool_round_identity, "candidate pool successor round identity", _IDENTITY_MAX)
        if self.candidate_identity is not None:
            require_canonical_text(self.candidate_identity, "replacement candidate identity", _IDENTITY_MAX)
        if self.matching_zero_candidate_proof is not None:
            if not isinstance(self.matching_zero_candidate_proof, MatchingZeroCandidateProof):
                raise TypeError("matching zero candidate proof is invalid")
            if self.matching_zero_candidate_proof.case_no != self.case_no:
                raise ServiceBeforeReplacementError("zero_candidate_owner_case_mismatch")

    @property
    def official_service_day_count(self) -> int:
        return len(self.actual_service_dates)

    @property
    def successor_round_identity(self) -> str | None:
        return self.successor_round.round_identity if self.successor_round is not None else None

    @property
    def reason_evidence_contract(self) -> ReplacementReasonEvidence:
        return ReplacementReasonEvidence(self.replacement_reason, self.reason_evidence)

    @property
    def prior_generation_version(self) -> int:
        return self.generation_version

    @property
    def prior_event_version(self) -> int:
        return self.event_version

    @property
    def prior_aggregate_version(self) -> int:
        return self.aggregate_version


@dataclass(frozen=True, slots=True)
class ServiceBeforeReplacementQuery:
    case_no: str
    scenario: ReplacementScenario
    actual_service_day_count: int
    actual_service_dates: tuple[date, ...]
    generation_version: int
    event_version: int
    impacted_root_ids: tuple[str, ...]
    retained_root_ids: tuple[str, ...]
    resume_step: ReplacementResumeStep
    blockers: tuple[str, ...]
    actual_service_proof: AuthoritativeActualServiceProof | None = None
    impacted_roots: tuple[ReplacementRootIdentity, ...] = ()
    retained_roots: tuple[ReplacementRootIdentity, ...] = ()
    root_delta: ReplacementRootDelta | None = None
    candidate_pool_reuse_proof: CandidatePoolReuseProof | None = None
    successor_round: SuccessorRoundFact | None = None
    prior_aggregate_identity: str | None = None
    aggregate_version: int = 0
    prior_generation_identity: str | None = None
    prior_event_identity: str | None = None
    matching_zero_candidate_proof: MatchingZeroCandidateProof | None = None


@dataclass(frozen=True, slots=True)
class ServiceBeforeReplacementCandidate:
    case_no: str
    scenario: ReplacementScenario
    outcome: ReplacementOutcome
    prior_generation_identity: str
    prior_event_identity: str
    replacement_generation_identity: str | None
    replacement_event_identity: str | None
    successor_round_identity: str | None
    expected_generation_version: int
    resulting_generation_version: int | None
    expected_event_version: int
    resulting_event_version: int | None
    retained_roots: tuple[ReplacementRootIdentity, ...]
    superseded_roots: tuple[ReplacementRootIdentity, ...]
    created_roots: tuple[ReplacementRootIdentity, ...]
    resume_step: ReplacementResumeStep
    candidate_pool_reuse_proof: CandidatePoolReuseProof | None
    actual_service_dates: tuple[date, ...]
    blockers: tuple[str, ...]
    fingerprint: PreviewFingerprint
    prior_aggregate_identity: str | None = None
    expected_aggregate_version: int = 0
    resulting_aggregate_version: int | None = None
    prior_case_no: str | None = None
    actual_service_proof: AuthoritativeActualServiceProof | None = None
    reason_evidence: ReplacementReasonEvidence | None = None
    projection_kind: ReplacementProjectionKind = ReplacementProjectionKind.SUCCESSOR_MATCHING
    successor_round_fact: SuccessorRoundFact | None = None
    matching_zero_candidate_proof: MatchingZeroCandidateProof | None = None

    @property
    def can_apply(self) -> bool:
        return self.outcome is ReplacementOutcome.READY and not self.blockers

    @property
    def zero_write(self) -> bool:
        return self.outcome is not ReplacementOutcome.READY

    @property
    def retained_root_ids(self) -> tuple[str, ...]:
        return tuple(item.root_id for item in self.retained_roots)

    @property
    def superseded_root_ids(self) -> tuple[str, ...]:
        return tuple(item.root_id for item in self.superseded_roots)

    @property
    def created_root_ids(self) -> tuple[str, ...]:
        return tuple(item.root_id for item in self.created_roots)

    @property
    def root_delta(self) -> ReplacementRootDelta:
        return ReplacementRootDelta(self.retained_roots, self.superseded_roots, self.created_roots)

    @property
    def prior_generation_version(self) -> int:
        return self.expected_generation_version

    @property
    def prior_event_version(self) -> int:
        return self.expected_event_version

    @property
    def prior_aggregate_version(self) -> int:
        return self.expected_aggregate_version


def query_service_before_replacement(facts: ServiceBeforeReplacementFacts) -> ServiceBeforeReplacementQuery:
    _require_facts(facts)
    blockers = _gate_blockers(facts)
    if (
        not blockers
        and facts.scenario is ReplacementScenario.R07
        and facts.successor_round is not None
        and facts.successor_round.candidate_count == 0
    ):
        blockers = ("zero_candidate_successor_disposition",)
    impacted = (
        ()
        if facts.scenario is ReplacementScenario.R07
        else _impacted_current_roots(facts)
    )
    retained = _retained_roots(facts, impacted if not blockers else ())
    return ServiceBeforeReplacementQuery(
        case_no=facts.case_no, scenario=facts.scenario, actual_service_day_count=facts.official_service_day_count,
        actual_service_dates=facts.actual_service_dates, generation_version=facts.generation_version,
        event_version=facts.event_version, impacted_root_ids=tuple(item.root_id for item in impacted),
        retained_root_ids=tuple(item.root_id for item in retained), resume_step=_server_resume_step(facts.candidate_pool_reuse, facts),
        blockers=blockers, actual_service_proof=facts.actual_service_proof, impacted_roots=impacted,
        retained_roots=retained, root_delta=ReplacementRootDelta(retained, impacted, ()) if not blockers else None,
        candidate_pool_reuse_proof=facts.candidate_pool_reuse, successor_round=facts.successor_round,
        prior_aggregate_identity=facts.prior_aggregate_identity, aggregate_version=facts.aggregate_version,
        prior_generation_identity=facts.prior_generation_identity,
        prior_event_identity=facts.prior_event_identity,
        matching_zero_candidate_proof=facts.matching_zero_candidate_proof,
    )


def preview_service_before_replacement(facts: ServiceBeforeReplacementFacts) -> ServiceBeforeReplacementCandidate:
    _require_facts(facts)
    blockers = _gate_blockers(facts)
    if blockers:
        outcome = ReplacementOutcome.SUBSTITUTION_REFERRAL if "actual_service_exists" in blockers else ReplacementOutcome.BLOCKED
        return _blocked_candidate(facts, outcome, blockers)
    if facts.scenario is ReplacementScenario.R07:
        round_fact = facts.successor_round
        if round_fact is not None:
            if round_fact.candidate_count != 0:
                return _blocked_candidate(facts, ReplacementOutcome.BLOCKED, ("zero_candidate_disposition_invalid",), successor_round=round_fact)
            return _build_r07_blocked_candidate(facts, round_fact)
        proof = facts.matching_zero_candidate_proof
        if proof is None:
            return _blocked_candidate(facts, ReplacementOutcome.BLOCKED, ("successor_round_missing",))
        return _build_r07_ready_candidate(facts, proof)

    impacted = _impacted_current_roots(facts)
    retained = _retained_roots(facts, impacted)
    generation_version = facts.generation_version + 1
    event_version = facts.event_version + 1
    aggregate_version = facts.aggregate_version + 1
    generation_identity = f"replacement-generation:{facts.case_no}:{generation_version}"
    event_identity = f"replacement-event:{facts.case_no}:{event_version}"
    round_identity = f"successor-round:{facts.case_no}:{event_version}"
    successor = ReplacementRootIdentity(ReplacementRootKind.SUCCESSOR_ROUND, round_identity, facts.case_no)
    created = (successor,)
    resume = _server_resume_step(facts.candidate_pool_reuse, facts)
    successor_reuse = _successor_reuse_proof(
        facts.candidate_pool_reuse,
        round_identity=round_identity,
        generation_version=facts.generation_version,
        event_version=facts.event_version,
    )
    projection_kind = ReplacementProjectionKind.MATCHING_ONLY_ZERO_SERVICE if facts.scenario is ReplacementScenario.R04 else ReplacementProjectionKind.SUCCESSOR_MATCHING
    candidate = ServiceBeforeReplacementCandidate(
        case_no=facts.case_no, scenario=facts.scenario, outcome=ReplacementOutcome.READY,
        prior_generation_identity=facts.prior_generation_identity, prior_event_identity=facts.prior_event_identity,
        replacement_generation_identity=generation_identity, replacement_event_identity=event_identity,
        successor_round_identity=round_identity, expected_generation_version=facts.generation_version,
        resulting_generation_version=generation_version, expected_event_version=facts.event_version,
        resulting_event_version=event_version, retained_roots=retained, superseded_roots=impacted,
        created_roots=created, resume_step=resume, candidate_pool_reuse_proof=successor_reuse,
        actual_service_dates=facts.actual_service_dates, blockers=(),
        fingerprint=_candidate_fingerprint(facts, generation_identity, event_identity, round_identity, retained, impacted, created, resume, candidate_pool_reuse=successor_reuse, expected_aggregate_version=facts.aggregate_version, resulting_aggregate_version=aggregate_version, projection_kind=projection_kind),
        prior_aggregate_identity=facts.prior_aggregate_identity, expected_aggregate_version=facts.aggregate_version,
        resulting_aggregate_version=aggregate_version, prior_case_no=facts.prior_case_no,
        actual_service_proof=facts.actual_service_proof, reason_evidence=facts.reason_evidence_contract,
        projection_kind=projection_kind,
    )
    _validate_candidate(candidate, facts)
    return candidate


build_service_before_replacement_candidate = preview_service_before_replacement


def _build_r07_ready_candidate(
    facts: ServiceBeforeReplacementFacts,
    proof: MatchingZeroCandidateProof,
) -> ServiceBeforeReplacementCandidate:
    generation_version = facts.generation_version + 1
    event_version = facts.event_version + 1
    aggregate_version = facts.aggregate_version + 1
    generation_identity = f"replacement-generation:{facts.case_no}:{generation_version}"
    event_identity = f"replacement-event:{facts.case_no}:{event_version}"
    round_identity = f"successor-round:{facts.case_no}:{event_version}"
    retained = _retained_roots(facts, ())
    created = (
        ReplacementRootIdentity(
            ReplacementRootKind.SUCCESSOR_ROUND,
            round_identity,
            facts.case_no,
        ),
    )
    candidate = ServiceBeforeReplacementCandidate(
        case_no=facts.case_no,
        scenario=facts.scenario,
        outcome=ReplacementOutcome.READY,
        prior_generation_identity=facts.prior_generation_identity,
        prior_event_identity=facts.prior_event_identity,
        replacement_generation_identity=generation_identity,
        replacement_event_identity=event_identity,
        successor_round_identity=round_identity,
        expected_generation_version=facts.generation_version,
        resulting_generation_version=generation_version,
        expected_event_version=facts.event_version,
        resulting_event_version=event_version,
        retained_roots=retained,
        superseded_roots=(),
        created_roots=created,
        resume_step=ReplacementResumeStep.STEP_2,
        candidate_pool_reuse_proof=None,
        actual_service_dates=facts.actual_service_dates,
        blockers=(),
        fingerprint=_candidate_fingerprint(
            facts,
            generation_identity,
            event_identity,
            round_identity,
            retained,
            (),
            created,
            ReplacementResumeStep.STEP_2,
            candidate_pool_reuse=None,
            expected_aggregate_version=facts.aggregate_version,
            resulting_aggregate_version=aggregate_version,
            projection_kind=ReplacementProjectionKind.SUCCESSOR_MATCHING,
        ),
        prior_aggregate_identity=facts.prior_aggregate_identity,
        expected_aggregate_version=facts.aggregate_version,
        resulting_aggregate_version=aggregate_version,
        prior_case_no=facts.prior_case_no,
        actual_service_proof=facts.actual_service_proof,
        reason_evidence=facts.reason_evidence_contract,
        matching_zero_candidate_proof=proof,
    )
    _validate_candidate(candidate, facts)
    return candidate


def _build_r07_blocked_candidate(facts: ServiceBeforeReplacementFacts, round_fact: SuccessorRoundFact) -> ServiceBeforeReplacementCandidate:
    retained = _retained_roots(facts, ())
    return ServiceBeforeReplacementCandidate(
        case_no=facts.case_no, scenario=facts.scenario, outcome=ReplacementOutcome.BLOCKED,
        prior_generation_identity=facts.prior_generation_identity, prior_event_identity=facts.prior_event_identity,
        replacement_generation_identity=round_fact.generation_identity, replacement_event_identity=round_fact.event_identity,
        successor_round_identity=round_fact.round_identity, expected_generation_version=facts.generation_version,
        resulting_generation_version=None, expected_event_version=facts.event_version, resulting_event_version=None,
        retained_roots=retained, superseded_roots=(), created_roots=(), resume_step=ReplacementResumeStep.STEP_2,
        candidate_pool_reuse_proof=facts.candidate_pool_reuse, actual_service_dates=facts.actual_service_dates,
        blockers=("zero_candidate_successor_disposition",),
        fingerprint=_candidate_fingerprint(facts, round_fact.generation_identity, round_fact.event_identity, round_fact.round_identity, retained, (), (), ReplacementResumeStep.STEP_2, candidate_pool_reuse=facts.candidate_pool_reuse, expected_aggregate_version=facts.aggregate_version, resulting_aggregate_version=None, projection_kind=ReplacementProjectionKind.SUCCESSOR_MATCHING, successor_round=round_fact),
        prior_aggregate_identity=facts.prior_aggregate_identity, expected_aggregate_version=facts.aggregate_version,
        prior_case_no=facts.prior_case_no, actual_service_proof=facts.actual_service_proof,
        reason_evidence=facts.reason_evidence_contract, successor_round_fact=round_fact,
    )


def _blocked_candidate(facts: ServiceBeforeReplacementFacts, outcome: ReplacementOutcome, blockers: tuple[str, ...], *, successor_round: SuccessorRoundFact | None = None) -> ServiceBeforeReplacementCandidate:
    retained = _retained_roots(facts, ())
    resume = _server_resume_step(facts.candidate_pool_reuse, facts)
    return ServiceBeforeReplacementCandidate(
        case_no=facts.case_no, scenario=facts.scenario, outcome=outcome,
        prior_generation_identity=facts.prior_generation_identity, prior_event_identity=facts.prior_event_identity,
        replacement_generation_identity=None, replacement_event_identity=None,
        successor_round_identity=successor_round.round_identity if successor_round else None,
        expected_generation_version=facts.generation_version, resulting_generation_version=None,
        expected_event_version=facts.event_version, resulting_event_version=None, retained_roots=retained,
        superseded_roots=(), created_roots=(), resume_step=resume, candidate_pool_reuse_proof=facts.candidate_pool_reuse,
        actual_service_dates=facts.actual_service_dates, blockers=tuple(blockers),
        fingerprint=_candidate_fingerprint(facts, None, None, successor_round.round_identity if successor_round else None, retained, (), (), resume, candidate_pool_reuse=facts.candidate_pool_reuse, expected_aggregate_version=facts.aggregate_version, resulting_aggregate_version=None, projection_kind=ReplacementProjectionKind.SUCCESSOR_MATCHING, blockers=tuple(blockers), successor_round=successor_round),
        prior_aggregate_identity=facts.prior_aggregate_identity, expected_aggregate_version=facts.aggregate_version,
        prior_case_no=facts.prior_case_no, actual_service_proof=facts.actual_service_proof,
        reason_evidence=facts.reason_evidence_contract, successor_round_fact=successor_round,
    )


def _require_facts(facts: ServiceBeforeReplacementFacts) -> None:
    if not isinstance(facts, ServiceBeforeReplacementFacts):
        raise TypeError("replacement facts are required")


def _gate_blockers(facts: ServiceBeforeReplacementFacts) -> tuple[str, ...]:
    if not facts.actual_service_proof_available or facts.actual_service_proof is None:
        return ("actual_service_proof_unavailable",)
    if facts.actual_service_proof.service_dates:
        return ("actual_service_exists",)
    try:
        _validate_required_roots(facts)
    except ServiceBeforeReplacementError as error:
        return (error.code,)
    if facts.candidate_pool_reuse is not None and not facts.candidate_pool_reuse.bound_to(facts):
        return ("candidate_pool_reuse_unbound",)
    if facts.scenario is ReplacementScenario.R07 and facts.successor_round is not None:
        round_fact = facts.successor_round
        if round_fact.generation_version <= facts.generation_version or round_fact.event_version <= facts.event_version:
            return ("successor_round_stale",)
        if round_fact.generation_identity == facts.prior_generation_identity or round_fact.event_identity == facts.prior_event_identity:
            return ("successor_round_identity_reused",)
    return ()


def _impacted_current_roots(facts: ServiceBeforeReplacementFacts) -> tuple[ReplacementRootIdentity, ...]:
    required = set(_IMPACTED_KINDS[facts.scenario])
    impacted = (
        item
        for item in facts.current_roots
        if item.kind in required and item.current and item.caregiver_bound
    )
    return tuple(sorted(impacted, key=lambda item: item.root_id))


def _validate_required_roots(facts: ServiceBeforeReplacementFacts) -> None:
    required = set(_IMPACTED_KINDS[facts.scenario])
    if facts.scenario is ReplacementScenario.R07:
        return
    impacted = _impacted_current_roots(facts)
    counts = {kind: 0 for kind in required}
    for item in impacted:
        counts[item.kind] += 1
    if any(count == 0 for count in counts.values()):
        raise ServiceBeforeReplacementError("replacement_root_set_incomplete")
    if any(count != 1 for count in counts.values()):
        raise ServiceBeforeReplacementError("replacement_root_kind_cardinality_invalid")


def _retained_roots(facts: ServiceBeforeReplacementFacts, impacted: Iterable[ReplacementRootIdentity]) -> tuple[ReplacementRootIdentity, ...]:
    impacted_ids = {item.root_id for item in impacted}
    roots = [item for item in facts.current_roots if item.root_id not in impacted_ids]
    roots.extend(facts.retained_history)
    unique = {item.root_id: item for item in roots}
    return tuple(unique[key] for key in sorted(unique))


def _server_resume_step(proof: CandidatePoolReuseProof | None, facts: ServiceBeforeReplacementFacts | None = None) -> ReplacementResumeStep:
    if proof is None or facts is None or not proof.bound_to(facts):
        return ReplacementResumeStep.STEP_2
    return ReplacementResumeStep.STEP_4 if proof.accepted_candidate else ReplacementResumeStep.STEP_3


def _candidate_fingerprint(facts: ServiceBeforeReplacementFacts, generation_identity: str | None, event_identity: str | None, round_identity: str | None, retained: tuple[ReplacementRootIdentity, ...], impacted: tuple[ReplacementRootIdentity, ...], created: tuple[ReplacementRootIdentity, ...], resume: ReplacementResumeStep, *, candidate_pool_reuse: CandidatePoolReuseProof | None, expected_aggregate_version: int, resulting_aggregate_version: int | None, projection_kind: ReplacementProjectionKind, blockers: tuple[str, ...] = (), successor_round: SuccessorRoundFact | None = None) -> PreviewFingerprint:
    payload = {
        "family": "service-before-replacement", "case_no": facts.case_no, "prior_case_no": facts.prior_case_no,
        "scenario": facts.scenario.value, "prior_aggregate_identity": facts.prior_aggregate_identity,
        "expected_aggregate_version": expected_aggregate_version, "resulting_aggregate_version": resulting_aggregate_version,
        "prior_generation_identity": facts.prior_generation_identity, "prior_event_identity": facts.prior_event_identity,
        "expected_generation_version": facts.generation_version, "expected_event_version": facts.event_version,
        "generation_identity": generation_identity, "event_identity": event_identity, "round_identity": round_identity,
        "actual_service_proof": facts.actual_service_proof.canonical_tuple if facts.actual_service_proof else None,
        "actual_service_dates": tuple(item.isoformat() for item in facts.actual_service_dates),
        "candidate_pool_reuse": candidate_pool_reuse.canonical_tuple if candidate_pool_reuse else None,
        "candidate_identity": candidate_pool_reuse.candidate_identity if candidate_pool_reuse else facts.candidate_identity,
        "retained": tuple(item.canonical_tuple for item in retained), "superseded": tuple(item.canonical_tuple for item in impacted),
        "created": tuple(item.canonical_tuple for item in created), "resume_step": resume.value,
        "projection_kind": projection_kind.value, "reason_evidence": facts.reason_evidence_contract.canonical_tuple,
        "blockers": blockers, "successor_round": successor_round.canonical_tuple if successor_round else None,
    }
    if facts.matching_zero_candidate_proof is not None:
        payload["matching_zero_candidate_proof"] = (
            facts.matching_zero_candidate_proof.canonical_tuple
        )
    return fingerprint_payload(payload)


def _successor_reuse_proof(
    source: CandidatePoolReuseProof | None,
    *,
    round_identity: str,
    generation_version: int,
    event_version: int,
) -> CandidatePoolReuseProof | None:
    if source is None:
        return None
    payload = {
        "pool_identity": source.pool_identity,
        "round_identity": round_identity,
        "coverage_version": source.coverage_version,
        "availability_version": source.availability_version,
        "willingness_version": source.willingness_version,
        "same_round": True,
        "coverage_valid": source.coverage_valid,
        "availability_valid": source.availability_valid,
        "willingness_valid": source.willingness_valid,
        "fresh": source.fresh,
        "accepted_candidate": source.accepted_candidate,
        "case_no": source.case_no,
        "successor_round_identity": round_identity,
        "generation_version": generation_version,
        "event_version": event_version,
        "candidate_identity": source.candidate_identity,
    }
    return CandidatePoolReuseProof(
        pool_identity=source.pool_identity,
        round_identity=round_identity,
        coverage_version=source.coverage_version,
        availability_version=source.availability_version,
        willingness_version=source.willingness_version,
        fingerprint=fingerprint_payload(payload),
        same_round=True,
        coverage_valid=source.coverage_valid,
        availability_valid=source.availability_valid,
        willingness_valid=source.willingness_valid,
        fresh=source.fresh,
        accepted_candidate=source.accepted_candidate,
        case_no=source.case_no,
        successor_round_identity=round_identity,
        generation_version=generation_version,
        event_version=event_version,
        candidate_identity=source.candidate_identity,
    )


def _validate_candidate(candidate: ServiceBeforeReplacementCandidate, facts: ServiceBeforeReplacementFacts) -> None:
    if candidate.resulting_generation_version is None or candidate.resulting_event_version is None or candidate.resulting_aggregate_version is None:
        raise ServiceBeforeReplacementError("replacement_resulting_version_missing")
    if candidate.resulting_generation_version <= facts.generation_version or candidate.resulting_event_version <= facts.event_version or candidate.resulting_aggregate_version <= facts.aggregate_version:
        raise ServiceBeforeReplacementError("replacement_version_not_newer")
    if candidate.prior_generation_identity == candidate.replacement_generation_identity or candidate.prior_event_identity == candidate.replacement_event_identity:
        raise ServiceBeforeReplacementError("replacement_identity_reused")
    if set(candidate.retained_root_ids) & set(candidate.superseded_root_ids):
        raise ServiceBeforeReplacementError("replacement_root_retained_and_superseded")
    if set(candidate.created_root_ids) & set(candidate.retained_root_ids) or set(candidate.created_root_ids) & set(candidate.superseded_root_ids):
        raise ServiceBeforeReplacementError("replacement_root_created_identity_reused")


def _validate_roots(roots: tuple[ReplacementRootIdentity, ...], case_no: str | None, label: str) -> None:
    if not isinstance(roots, tuple):
        raise TypeError(f"{label} must be a tuple")
    if any(not isinstance(item, ReplacementRootIdentity) for item in roots):
        raise TypeError(f"{label} contain an invalid root")
    if case_no is not None and any(item.case_no != case_no for item in roots):
        raise ServiceBeforeReplacementError("replacement_root_case_mismatch")
    if len({item.root_id for item in roots}) != len(roots):
        raise ServiceBeforeReplacementError("replacement_root_identity_not_unique")


def _validate_text_tuple(values: tuple[str, ...], label: str, maximum: int) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label}s must be a tuple")
    for value in values:
        require_canonical_text(value, label, maximum)


def _validate_dates(values: tuple[date, ...], label: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} must be a tuple")
    if any(type(item) is not date for item in values):
        raise TypeError(f"{label} must contain dates")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be sorted and unique")


__all__ = [
    "ActualServiceProof", "AuthoritativeActualServiceProof", "CandidatePoolReuseProof", "ExistingSuccessorRound", "OfficialServiceProof",
    "ReplacementOutcome", "ReplacementProjectionKind", "ReplacementReasonEvidence", "ReplacementResumeStep", "ReplacementRootDelta",
    "MatchingZeroCandidateProof", "ReplacementRootIdentity", "ReplacementRootKind", "ReplacementScenario", "ServiceBeforeReplacementCandidate", "ServiceBeforeReplacementError",
    "ServiceBeforeReplacementFacts", "ServiceBeforeReplacementQuery", "SuccessorRoundFact", "build_service_before_replacement_candidate",
    "preview_service_before_replacement", "query_service_before_replacement",
]

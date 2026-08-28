"""
File: service_before_replacement_projection.py
Description: 以 1012 fresh readback 純投影服務前換人異常狀態。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from domains.scheduling.service_before_replacement import (
    AuthoritativeActualServiceProof,
    CandidatePoolReuseProof,
    ReplacementScenario,
    ReplacementRootKind,
    _IMPACTED_KINDS,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


class ServiceBeforeReplacementProjectionStatus(StrEnum):
    TERMINAL = "terminal"
    BLOCKED = "blocked"
    ACTIVE = "active"
    OUTCOME_UNKNOWN = "outcome_unknown"


class ServiceBeforeReplacementProjectionAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class ServiceBeforeReplacementProjectionError(ValueError):
    """A projector input is not the typed 1012 readback contract."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ReplacementLineageReadback:
    case_no: str
    scenario: ReplacementScenario | str
    prior_generation_identity: str
    replacement_generation_identity: str
    prior_event_identity: str
    replacement_event_identity: str
    expected_aggregate_version: int
    resulting_aggregate_version: int
    expected_generation_version: int
    resulting_generation_version: int
    expected_event_version: int
    resulting_event_version: int
    complete: bool = True
    fresh: bool = True

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "replacement lineage case number", 50)
        try:
            scenario = (
                self.scenario
                if isinstance(self.scenario, ReplacementScenario)
                else ReplacementScenario(self.scenario)
            )
        except (TypeError, ValueError) as error:
            raise ServiceBeforeReplacementProjectionError("lineage_scenario_invalid") from error
        object.__setattr__(self, "scenario", scenario)
        for value, label in (
            (self.prior_generation_identity, "prior generation identity"),
            (self.replacement_generation_identity, "replacement generation identity"),
            (self.prior_event_identity, "prior event identity"),
            (self.replacement_event_identity, "replacement event identity"),
        ):
            require_canonical_text(value, label, 191)
        for value, label in (
            (self.expected_aggregate_version, "expected aggregate version"),
            (self.resulting_aggregate_version, "resulting aggregate version"),
            (self.expected_generation_version, "expected generation version"),
            (self.resulting_generation_version, "resulting generation version"),
            (self.expected_event_version, "expected event version"),
            (self.resulting_event_version, "resulting event version"),
        ):
            require_nonnegative_integer(value, label)
        if type(self.complete) is not bool or type(self.fresh) is not bool:
            raise TypeError("replacement lineage readback flags must be bool")


@dataclass(frozen=True, slots=True)
class ReplacementRootReadback:
    root_identity: str
    owner_domain: Literal["scheduling", "matching"]
    root_kind: ReplacementRootKind | str
    disposition: Literal["retained", "superseded", "created"]
    current: bool
    case_no: str
    caregiver_bound: bool = True
    complete: bool = True

    def __post_init__(self) -> None:
        require_canonical_text(self.root_identity, "replacement root identity", 191)
        require_canonical_text(self.case_no, "replacement root case number", 50)
        if self.owner_domain not in {"scheduling", "matching"}:
            raise ServiceBeforeReplacementProjectionError("root_owner_invalid")
        try:
            kind = (
                self.root_kind
                if isinstance(self.root_kind, ReplacementRootKind)
                else ReplacementRootKind(self.root_kind)
            )
        except (TypeError, ValueError) as error:
            raise ServiceBeforeReplacementProjectionError("root_kind_invalid") from error
        object.__setattr__(self, "root_kind", kind)
        if self.disposition not in {"retained", "superseded", "created"}:
            raise ServiceBeforeReplacementProjectionError("root_disposition_invalid")
        if type(self.current) is not bool or type(self.caregiver_bound) is not bool or type(self.complete) is not bool:
            raise TypeError("replacement root readback flags must be bool")
        allowed = {
            "matching": {
                ReplacementRootKind.CANDIDATE_BINDING,
                ReplacementRootKind.WILLINGNESS,
                ReplacementRootKind.MATCHING_PLAN,
                ReplacementRootKind.MATCHING_SEGMENT,
                ReplacementRootKind.MATCHING_REPLY,
                ReplacementRootKind.RECIPIENT_CONFIRMATION,
                ReplacementRootKind.SUCCESSOR_ROUND,
            },
            "scheduling": {
                ReplacementRootKind.WAITING_LOCK,
                ReplacementRootKind.COMMITMENT,
                ReplacementRootKind.SIGNBACK,
                ReplacementRootKind.RECIPIENT_BINDING,
                ReplacementRootKind.EFFECTIVE_GENERATION,
                ReplacementRootKind.ASSIGNMENT,
                ReplacementRootKind.OFFICIAL_SCHEDULE,
            },
        }
        if kind not in allowed[self.owner_domain]:
            raise ServiceBeforeReplacementProjectionError("root_owner_kind_mismatch")


@dataclass(frozen=True, slots=True)
class ReplacementSuccessorReadback:
    case_no: str
    replacement_event_identity: str
    successor_round_identity: str
    candidate_count: int
    resume_step: str
    matching_package_lineage_id: int
    matching_event_id: int
    zero_candidate_disposition: str | None = None
    complete: bool = True
    fresh: bool = True
    candidate_pool_reuse_proof: CandidatePoolReuseProof | None = None

    def __post_init__(self) -> None:
        for value, label, limit in (
            (self.case_no, "successor case number", 50),
            (self.replacement_event_identity, "successor event identity", 191),
            (self.successor_round_identity, "successor round identity", 191),
        ):
            require_canonical_text(value, label, limit)
        require_nonnegative_integer(self.candidate_count, "successor candidate count")
        require_nonnegative_integer(self.matching_package_lineage_id, "matching package lineage id")
        require_nonnegative_integer(self.matching_event_id, "matching event id")
        if self.resume_step not in {"step_2", "step_3", "step_4"}:
            raise ServiceBeforeReplacementProjectionError("successor_resume_step_invalid")
        if self.candidate_count == 0:
            if self.zero_candidate_disposition not in {
                None,
                "blocked_no_candidate",
            }:
                raise ServiceBeforeReplacementProjectionError("successor_zero_candidate_disposition_invalid")
        elif self.zero_candidate_disposition is not None:
            raise ServiceBeforeReplacementProjectionError("successor_zero_candidate_disposition_unexpected")
        if self.matching_package_lineage_id <= 0 or self.matching_event_id <= 0:
            raise ServiceBeforeReplacementProjectionError("successor_matching_binding_invalid")
        if type(self.complete) is not bool or type(self.fresh) is not bool:
            raise TypeError("replacement successor readback flags must be bool")
        if self.candidate_pool_reuse_proof is not None and not isinstance(
            self.candidate_pool_reuse_proof, CandidatePoolReuseProof
        ):
            raise TypeError("replacement successor candidate pool reuse proof is invalid")


@dataclass(frozen=True, slots=True)
class ReplacementReceiptReadback:
    case_no: str
    receipt_identity: str
    replacement_event_identity: str
    successor_round_identity: str
    resulting_aggregate_version: int
    resulting_generation_version: int
    resulting_event_version: int
    outbox_identity: str
    retained_root_ids: tuple[str, ...]
    superseded_root_ids: tuple[str, ...]
    created_root_ids: tuple[str, ...]
    retained_root_set_digest: str | None = None
    superseded_root_set_digest: str | None = None
    created_root_set_digest: str | None = None
    retained_root_count: int | None = None
    superseded_root_count: int | None = None
    created_root_count: int | None = None
    result_state: str = "applied"
    complete: bool = True
    fresh: bool = True

    def __post_init__(self) -> None:
        for value, label, limit in (
            (self.case_no, "receipt case number", 50),
            (self.receipt_identity, "receipt identity", 191),
            (self.replacement_event_identity, "receipt event identity", 191),
            (self.successor_round_identity, "receipt successor identity", 191),
            (self.outbox_identity, "receipt outbox identity", 191),
        ):
            require_canonical_text(value, label, limit)
        for value, label in (
            (self.resulting_aggregate_version, "receipt aggregate version"),
            (self.resulting_generation_version, "receipt generation version"),
            (self.resulting_event_version, "receipt event version"),
        ):
            require_nonnegative_integer(value, label)
        for values, label in (
            (self.retained_root_ids, "receipt retained root ids"),
            (self.superseded_root_ids, "receipt superseded root ids"),
            (self.created_root_ids, "receipt created root ids"),
        ):
            _validate_ids(values, label)
        if self.result_state != "applied":
            raise ServiceBeforeReplacementProjectionError("receipt_result_state_invalid")
        if type(self.complete) is not bool or type(self.fresh) is not bool:
            raise TypeError("replacement receipt readback flags must be bool")


@dataclass(frozen=True, slots=True)
class ReplacementOutboxReadback:
    case_no: str
    replacement_event_identity: str
    receipt_identity: str
    outbox_identity: str
    intent_type: str = "successor_projection_readback_requested"
    target_owner: str = "orders_anomalies_projection"
    complete: bool = True
    fresh: bool = True

    def __post_init__(self) -> None:
        for value, label, limit in (
            (self.case_no, "outbox case number", 50),
            (self.replacement_event_identity, "outbox event identity", 191),
            (self.receipt_identity, "outbox receipt identity", 191),
            (self.outbox_identity, "outbox identity", 191),
        ):
            require_canonical_text(value, label, limit)
        if self.intent_type != "successor_projection_readback_requested":
            raise ServiceBeforeReplacementProjectionError("outbox_intent_invalid")
        if self.target_owner != "orders_anomalies_projection":
            raise ServiceBeforeReplacementProjectionError("outbox_target_invalid")
        if type(self.complete) is not bool or type(self.fresh) is not bool:
            raise TypeError("replacement outbox readback flags must be bool")


@dataclass(frozen=True, slots=True)
class CurrentStepOwnerReadback:
    case_no: str
    current_step: int
    complete: bool = True
    fresh: bool = True

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "current-step case number", 50)
        require_nonnegative_integer(self.current_step, "current step")
        if type(self.complete) is not bool or type(self.fresh) is not bool:
            raise TypeError("current-step readback flags must be bool")


@dataclass(frozen=True, slots=True)
class ServiceBeforeReplacementProjectionInput:
    lineage: ReplacementLineageReadback
    roots: tuple[ReplacementRootReadback, ...] | None
    successor: ReplacementSuccessorReadback | None
    receipt: ReplacementReceiptReadback | None
    outbox: ReplacementOutboxReadback | None
    actual_service_proof: AuthoritativeActualServiceProof | None
    current_step: CurrentStepOwnerReadback | None

    def __post_init__(self) -> None:
        if not isinstance(self.lineage, ReplacementLineageReadback):
            raise TypeError("replacement projection lineage is invalid")
        for value, label in (
            (self.successor, "successor"),
            (self.receipt, "receipt"),
            (self.outbox, "outbox"),
            (self.actual_service_proof, "actual service proof"),
        ):
            if value is None:
                continue
            if not isinstance(value, {
                "lineage": ReplacementLineageReadback,
                "successor": ReplacementSuccessorReadback,
                "receipt": ReplacementReceiptReadback,
                "outbox": ReplacementOutboxReadback,
                "actual service proof": AuthoritativeActualServiceProof,
            }[label]):
                raise TypeError(f"replacement projection {label} is invalid")
        if self.roots is not None and (
            not isinstance(self.roots, tuple)
            or any(not isinstance(root, ReplacementRootReadback) for root in self.roots)
        ):
            raise TypeError("replacement projection roots are invalid")
        if self.current_step is not None and not isinstance(self.current_step, CurrentStepOwnerReadback):
            raise TypeError("replacement projection current-step readback is invalid")


@dataclass(frozen=True, slots=True)
class ServiceBeforeReplacementOccurrenceProjection:
    occurrence_identity: str
    case_no: str
    scenario: ReplacementScenario
    status: ServiceBeforeReplacementProjectionStatus
    blockers: tuple[str, ...]
    current_step: int | None
    availability: ServiceBeforeReplacementProjectionAvailability
    error_code: str | None
    replacement_event_identity: str | None
    successor_round_identity: str | None
    retained_root_ids: tuple[str, ...]
    superseded_root_ids: tuple[str, ...]
    created_root_ids: tuple[str, ...]
    projection_fingerprint: PreviewFingerprint

    @property
    def terminal(self) -> bool:
        return self.status is ServiceBeforeReplacementProjectionStatus.TERMINAL

    @property
    def available(self) -> bool:
        return self.availability is ServiceBeforeReplacementProjectionAvailability.AVAILABLE

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return self.projection_fingerprint

    @property
    def outcome(self) -> str:
        """Expose the Scheduling referral outcome without changing anomaly status semantics."""

        if "actual_service_exists" in self.blockers:
            return "substitution_referral"
        return self.status.value

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "occurrence_identity": self.occurrence_identity,
            "case_no": self.case_no,
            "scenario": self.scenario.value,
            "status": self.status.value,
            "outcome": self.outcome,
            "blockers": self.blockers,
            "current_step": self.current_step,
            "availability": self.availability.value,
            "error_code": self.error_code,
            "replacement_event_identity": self.replacement_event_identity,
            "successor_round_identity": self.successor_round_identity,
            "retained_root_ids": self.retained_root_ids,
            "superseded_root_ids": self.superseded_root_ids,
            "created_root_ids": self.created_root_ids,
        }


def project_service_before_replacement_occurrence(
    source: ServiceBeforeReplacementProjectionInput,
) -> ServiceBeforeReplacementOccurrenceProjection:
    """Project one exact 1012 readback without writes or inferred business facts."""

    if not isinstance(source, ServiceBeforeReplacementProjectionInput):
        raise TypeError("replacement projection input is invalid")
    lineage = source.lineage
    occurrence_identity = _occurrence_identity(lineage)
    base = dict(
        occurrence_identity=occurrence_identity,
        case_no=lineage.case_no,
        scenario=lineage.scenario,
        current_step=None if source.current_step is None else source.current_step.current_step,
        replacement_event_identity=lineage.replacement_event_identity,
        successor_round_identity=(
            None if source.successor is None else source.successor.successor_round_identity
        ),
        retained_root_ids=(
            ()
            if source.receipt is None
            else tuple(sorted(source.receipt.retained_root_ids))
        ),
        superseded_root_ids=(
            ()
            if source.receipt is None
            else tuple(sorted(source.receipt.superseded_root_ids))
        ),
        created_root_ids=(
            ()
            if source.receipt is None
            else tuple(sorted(source.receipt.created_root_ids))
        ),
    )

    lineage_issue = _lineage_identity_issue(lineage)
    if lineage_issue is not None:
        return _result(
            {**base, "replacement_event_identity": None},
            ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN,
            (lineage_issue,),
            ServiceBeforeReplacementProjectionAvailability.UNAVAILABLE,
            lineage_issue,
            source=source,
        )

    proof = source.actual_service_proof
    if proof is not None:
        proof_issue = _actual_service_proof_issue(proof, lineage.case_no)
        if proof_issue is not None:
            return _result(
                {**base, "replacement_event_identity": None},
                ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN,
                (proof_issue,),
                ServiceBeforeReplacementProjectionAvailability.UNAVAILABLE,
                proof_issue,
                source=source,
            )
        if proof.service_dates:
            return _result(
                {
                    **base,
                    "current_step": None,
                    "replacement_event_identity": None,
                    "successor_round_identity": None,
                    "retained_root_ids": (),
                    "superseded_root_ids": (),
                    "created_root_ids": (),
                },
                ServiceBeforeReplacementProjectionStatus.ACTIVE,
                ("actual_service_exists",),
                ServiceBeforeReplacementProjectionAvailability.AVAILABLE,
                None,
                source=source,
            )

    issue = _contract_issue(source)
    if issue is not None:
        return _result(
            base,
            ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN,
            (issue,),
            ServiceBeforeReplacementProjectionAvailability.UNAVAILABLE,
            issue,
            source=source,
        )
    if lineage.scenario is ReplacementScenario.R07:
        if source.current_step.current_step != 2:
            return _result(
                base,
                ServiceBeforeReplacementProjectionStatus.ACTIVE,
                ("r07_current_step_not_step_2",),
                ServiceBeforeReplacementProjectionAvailability.AVAILABLE,
                None,
                source=source,
            )
        return _result(
            base,
            ServiceBeforeReplacementProjectionStatus.BLOCKED,
            ("zero_candidate_successor",),
            ServiceBeforeReplacementProjectionAvailability.AVAILABLE,
            None,
            source=source,
        )
    if source.successor is None:
        return _result(
            base,
            ServiceBeforeReplacementProjectionStatus.ACTIVE,
            ("successor_missing",),
            ServiceBeforeReplacementProjectionAvailability.AVAILABLE,
            None,
            source=source,
        )
    if source.successor.candidate_count == 0:
        return _result(
            base,
            ServiceBeforeReplacementProjectionStatus.ACTIVE,
            ("successor_candidate_pool_empty",),
            ServiceBeforeReplacementProjectionAvailability.AVAILABLE,
            None,
            source=source,
        )
    if source.current_step.current_step not in {2, 3, 4}:
        return _result(
            base,
            ServiceBeforeReplacementProjectionStatus.ACTIVE,
            ("current_step_not_replacement_gate",),
            ServiceBeforeReplacementProjectionAvailability.AVAILABLE,
            None,
            source=source,
        )
    if source.current_step.current_step != int(source.successor.resume_step[-1]):
        return _result(
            base,
            ServiceBeforeReplacementProjectionStatus.ACTIVE,
            ("successor_resume_step_mismatch",),
            ServiceBeforeReplacementProjectionAvailability.AVAILABLE,
            None,
            source=source,
        )
    return _result(
        base,
        ServiceBeforeReplacementProjectionStatus.TERMINAL,
        (),
        ServiceBeforeReplacementProjectionAvailability.AVAILABLE,
        None,
        source=source,
    )


project_service_before_replacement = project_service_before_replacement_occurrence
project_replacement_occurrence = project_service_before_replacement_occurrence
project_service_before_replacement_projection = project_service_before_replacement_occurrence


def _contract_issue(source: ServiceBeforeReplacementProjectionInput) -> str | None:
    lineage, successor, receipt, outbox, proof, current = (
        source.lineage,
        source.successor,
        source.receipt,
        source.outbox,
        source.actual_service_proof,
        source.current_step,
    )
    if not lineage.complete or not lineage.fresh:
        return "lineage_readback_unavailable"
    if successor is None:
        return "replacement_successor_readback_unavailable"
    if receipt is None:
        return "replacement_receipt_readback_unavailable"
    if outbox is None:
        return "replacement_outbox_readback_unavailable"
    if proof is None:
        return "actual_service_proof_unavailable"
    if not successor.complete or not successor.fresh:
        return "successor_readback_unavailable"
    if not receipt.complete or not receipt.fresh:
        return "receipt_readback_unavailable"
    if not outbox.complete or not outbox.fresh:
        return "outbox_readback_unavailable"
    if current is None:
        return "current_step_readback_unavailable"
    if not current.complete or not current.fresh:
        return "current_step_readback_unavailable"
    case_no = lineage.case_no
    if any(
        value.case_no != case_no
        for value in (successor, receipt, outbox, proof, current)
    ):
        return "replacement_readback_cross_case"
    if not _identity_case_bound(proof.source_identity, case_no):
        return "replacement_identity_case_mismatch"
    if any(
        not _identity_case_bound(identity, case_no)
        for identity in (
            successor.replacement_event_identity,
            successor.successor_round_identity,
            receipt.receipt_identity,
            receipt.replacement_event_identity,
            receipt.successor_round_identity,
            receipt.outbox_identity,
            outbox.replacement_event_identity,
            outbox.receipt_identity,
            outbox.outbox_identity,
        )
    ):
        return "replacement_identity_case_mismatch"
    if proof.source_version <= 0:
        return "actual_service_proof_unavailable"
    if proof.service_dates and proof.fingerprint is None:
        return "actual_service_proof_unavailable"
    if lineage.resulting_aggregate_version <= lineage.expected_aggregate_version:
        return "replacement_aggregate_version_stale"
    if lineage.resulting_generation_version <= lineage.expected_generation_version:
        return "replacement_generation_version_stale"
    if lineage.resulting_event_version <= lineage.expected_event_version:
        return "replacement_event_version_stale"
    if (
        lineage.prior_generation_identity == lineage.replacement_generation_identity
        or lineage.prior_event_identity == lineage.replacement_event_identity
    ):
        return "replacement_prior_binding_invalid"
    if successor.replacement_event_identity != lineage.replacement_event_identity:
        return "replacement_successor_event_mismatch"
    if receipt.replacement_event_identity != lineage.replacement_event_identity:
        return "replacement_receipt_event_mismatch"
    if receipt.successor_round_identity != successor.successor_round_identity:
        return "replacement_receipt_successor_mismatch"
    if outbox.replacement_event_identity != lineage.replacement_event_identity:
        return "replacement_outbox_event_mismatch"
    if outbox.receipt_identity != receipt.receipt_identity or outbox.outbox_identity != receipt.outbox_identity:
        return "replacement_outbox_receipt_mismatch"
    if (
        receipt.resulting_aggregate_version != lineage.resulting_aggregate_version
        or receipt.resulting_generation_version != lineage.resulting_generation_version
        or receipt.resulting_event_version != lineage.resulting_event_version
    ):
        return "replacement_receipt_version_mismatch"
    roots = source.roots or ()
    if not roots or any(not root.complete for root in roots):
        return "replacement_root_readback_unavailable"
    if len({root.root_identity for root in roots}) != len(roots):
        return "replacement_root_identity_duplicate"
    if any(root.case_no != case_no for root in roots):
        return "replacement_root_cross_case"
    if any(not _identity_case_bound(root.root_identity, case_no) for root in roots):
        return "replacement_identity_case_mismatch"
    sets = {
        "retained": tuple(sorted(root.root_identity for root in roots if root.disposition == "retained")),
        "superseded": tuple(sorted(root.root_identity for root in roots if root.disposition == "superseded")),
        "created": tuple(sorted(root.root_identity for root in roots if root.disposition == "created")),
    }
    for key, values in sets.items():
        if values != tuple(sorted(getattr(receipt, f"{key}_root_ids"))):
            return "replacement_root_set_mismatch"
        digest = getattr(receipt, f"{key}_root_set_digest")
        count = getattr(receipt, f"{key}_root_count")
        if digest is None or count is None or digest != _root_set_digest(values) or count != len(values):
            return "replacement_root_set_digest_mismatch"
    if any(root.current for root in roots if root.disposition == "retained"):
        return "replacement_old_caregiver_root_still_current"
    created = [root for root in roots if root.disposition == "created"]
    if lineage.scenario is not ReplacementScenario.R07:
        required = set(_IMPACTED_KINDS[lineage.scenario])
        superseded = [root for root in roots if root.disposition == "superseded"]
        superseded_counts = {
            kind: sum(1 for root in superseded if root.root_kind is kind)
            for kind in required
        }
        if (
            {root.root_kind for root in superseded} != required
            or any(count != 1 for count in superseded_counts.values())
            or any(root.current or not root.caregiver_bound for root in superseded)
        ):
            return "replacement_root_kind_cardinality_invalid"
    elif any(root.disposition == "superseded" for root in roots):
        return "replacement_root_set_mismatch"
    if len(created) != 1 or created[0].root_kind is not ReplacementRootKind.SUCCESSOR_ROUND:
        return "replacement_successor_root_mismatch"
    if any(
        root.current
        for root in roots
        if root.disposition in {"retained", "superseded"} and root.caregiver_bound
    ):
        return "replacement_old_caregiver_root_still_current"
    if not any(root.disposition == "retained" and root.caregiver_bound for root in roots):
        return "replacement_old_caregiver_root_missing"
    successor_roots = [root for root in created if root.root_kind is ReplacementRootKind.SUCCESSOR_ROUND]
    if len(successor_roots) != 1 or successor_roots[0].root_identity != successor.successor_round_identity:
        return "replacement_successor_root_mismatch"
    if not successor_roots[0].current:
        return "replacement_successor_not_current"
    if lineage.scenario is ReplacementScenario.R07:
        if (
            successor.candidate_count != 0
            or successor.zero_candidate_disposition != "blocked_no_candidate"
            or successor.resume_step != "step_2"
        ):
            return "replacement_r07_disposition_invalid"
    elif successor.zero_candidate_disposition is not None:
        return "replacement_zero_candidate_disposition_invalid"
    if current.current_step in {3, 4}:
        reuse = successor.candidate_pool_reuse_proof
        if reuse is None or not reuse.reusable:
            return "replacement_candidate_pool_reuse_unavailable"
        if (
            reuse.case_no != case_no
            or reuse.round_identity != successor.successor_round_identity
            or reuse.successor_round_identity != successor.successor_round_identity
            or not _identity_case_bound(reuse.pool_identity, case_no)
            or not _identity_case_bound(reuse.candidate_identity, case_no)
            or reuse.generation_version != lineage.expected_generation_version
            or reuse.event_version != lineage.expected_event_version
            or reuse.accepted_candidate != (current.current_step == 4)
        ):
            return "replacement_candidate_pool_reuse_unavailable"
    return None


def _result(
    base: dict[str, object],
    status: ServiceBeforeReplacementProjectionStatus,
    blockers: tuple[str, ...],
    availability: ServiceBeforeReplacementProjectionAvailability,
    error_code: str | None,
    *,
    source: ServiceBeforeReplacementProjectionInput | None = None,
):
    payload = {
        **base,
        "status": status.value,
        "blockers": tuple(blockers),
        "availability": availability.value,
        "error_code": error_code,
    }
    if source is not None:
        payload["canonical_readback"] = _canonical_readback_payload(source)
    result = ServiceBeforeReplacementOccurrenceProjection(
        **base,
        status=status,
        blockers=tuple(blockers),
        availability=availability,
        error_code=error_code,
        projection_fingerprint=fingerprint_payload(payload),
    )
    return result


def _occurrence_identity(lineage: ReplacementLineageReadback) -> str:
    identity_digest = fingerprint_payload(
        {
            "case_no": lineage.case_no,
            "scenario": lineage.scenario.value,
            "replacement_event_identity": lineage.replacement_event_identity,
        }
    ).value
    return f"service-before-replacement:{identity_digest}"


def _lineage_identity_issue(lineage: ReplacementLineageReadback) -> str | None:
    if any(
        not _identity_case_bound(identity, lineage.case_no)
        for identity in (
            lineage.prior_generation_identity,
            lineage.replacement_generation_identity,
            lineage.prior_event_identity,
            lineage.replacement_event_identity,
        )
    ):
        return "replacement_identity_case_mismatch"
    return None


def _actual_service_proof_issue(
    proof: AuthoritativeActualServiceProof, case_no: str
) -> str | None:
    if proof.case_no != case_no:
        return "replacement_readback_cross_case"
    if proof.source_version <= 0 or not _identity_case_bound(proof.source_identity, case_no):
        return "actual_service_proof_unavailable"
    return None


def _identity_case_bound(identity: str, case_no: str) -> bool:
    """Require an exact case token with canonical identity boundaries."""

    return (
        identity == case_no
        or identity.startswith(f"{case_no}:")
        or identity.endswith(f":{case_no}")
        or f":{case_no}:" in identity
    )


def _canonical_readback_payload(
    source: ServiceBeforeReplacementProjectionInput,
) -> dict[str, object]:
    lineage = source.lineage
    proof = source.actual_service_proof
    successor = source.successor
    receipt = source.receipt
    outbox = source.outbox
    current = source.current_step
    return {
        "lineage": (
            lineage.case_no,
            lineage.scenario.value,
            lineage.prior_generation_identity,
            lineage.replacement_generation_identity,
            lineage.prior_event_identity,
            lineage.replacement_event_identity,
            lineage.expected_aggregate_version,
            lineage.resulting_aggregate_version,
            lineage.expected_generation_version,
            lineage.resulting_generation_version,
            lineage.expected_event_version,
            lineage.resulting_event_version,
            lineage.complete,
            lineage.fresh,
        ),
        "roots": tuple(
            (
                root.root_identity,
                root.owner_domain,
                root.root_kind.value,
                root.disposition,
                root.current,
                root.case_no,
                root.caregiver_bound,
                root.complete,
            )
            for root in sorted(
                source.roots or (),
                key=lambda root: (
                    root.root_identity,
                    root.owner_domain,
                    root.root_kind.value,
                    root.disposition,
                    root.current,
                    root.case_no,
                    root.caregiver_bound,
                    root.complete,
                ),
            )
        ),
        "successor": None
        if successor is None
        else (
            successor.case_no,
            successor.replacement_event_identity,
            successor.successor_round_identity,
            successor.candidate_count,
            successor.resume_step,
            successor.matching_package_lineage_id,
            successor.matching_event_id,
            successor.zero_candidate_disposition,
            successor.complete,
            successor.fresh,
            None
            if successor.candidate_pool_reuse_proof is None
            else successor.candidate_pool_reuse_proof.canonical_tuple,
        ),
        "receipt": None
        if receipt is None
        else (
            receipt.case_no,
            receipt.receipt_identity,
            receipt.replacement_event_identity,
            receipt.successor_round_identity,
            receipt.resulting_aggregate_version,
            receipt.resulting_generation_version,
            receipt.resulting_event_version,
            receipt.outbox_identity,
            tuple(sorted(receipt.retained_root_ids)),
            tuple(sorted(receipt.superseded_root_ids)),
            tuple(sorted(receipt.created_root_ids)),
            receipt.retained_root_set_digest,
            receipt.superseded_root_set_digest,
            receipt.created_root_set_digest,
            receipt.retained_root_count,
            receipt.superseded_root_count,
            receipt.created_root_count,
            receipt.result_state,
            receipt.complete,
            receipt.fresh,
        ),
        "outbox": None
        if outbox is None
        else (
            outbox.case_no,
            outbox.replacement_event_identity,
            outbox.receipt_identity,
            outbox.outbox_identity,
            outbox.intent_type,
            outbox.target_owner,
            outbox.complete,
            outbox.fresh,
        ),
        "actual_service_proof": None if proof is None else proof.canonical_tuple,
        "current_step": None
        if current is None
        else (current.case_no, current.current_step, current.complete, current.fresh),
    }


def _root_set_digest(values: tuple[str, ...]) -> str:
    return sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()


def _validate_ids(values: tuple[str, ...], label: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} must be a tuple")
    for value in values:
        require_canonical_text(value, label, 191)
    if len(set(values)) != len(values):
        raise ServiceBeforeReplacementProjectionError(f"{label}_duplicate")


__all__ = [
    "CurrentStepOwnerReadback",
    "ReplacementLineageReadback",
    "ReplacementOutboxReadback",
    "ReplacementReceiptReadback",
    "ReplacementRootReadback",
    "ReplacementSuccessorReadback",
    "ServiceBeforeReplacementOccurrenceProjection",
    "ServiceBeforeReplacementProjectionAvailability",
    "ServiceBeforeReplacementProjectionError",
    "ServiceBeforeReplacementProjectionInput",
    "ServiceBeforeReplacementProjectionStatus",
    "project_replacement_occurrence",
    "project_service_before_replacement",
    "project_service_before_replacement_occurrence",
    "project_service_before_replacement_projection",
]

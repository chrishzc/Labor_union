"""
File: service_before_replacement.py
Description: 定義服務前換人 Scheduling Q/P/A 的嚴格 typed 公開模型。
"""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from domains.scheduling.service_before_replacement import (
    AuthoritativeActualServiceProof,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


_Fingerprint = str
_Outcome = Literal["ready", "blocked", "substitution_referral"]
_Scenario = Literal["R-01", "R-02", "R-03", "R-04", "R-07"]
_Step = Literal["step_2", "step_3", "step_4"]
_Projection = Literal["successor_matching", "matching_only_zero_service"]
_RootKind = Literal[
    "candidate_binding", "willingness", "matching_plan", "matching_segment",
    "matching_reply", "recipient_confirmation", "waiting_lock", "commitment",
    "signback", "recipient_binding", "effective_generation", "assignment",
    "official_schedule", "successor_round",
]
_ErrorCategory = Literal[
    "validation", "forbidden", "not_found", "domain_blocked", "conflict",
    "idempotency_mismatch", "unavailable", "internal",
]
_ErrorCode = Literal[
    "replacement_blocked", "replacement_actual_service_exists", "replacement_version_conflict",
    "replacement_identity_drift", "replacement_reason_evidence_drift", "replacement_preview_stale",
    "replacement_idempotency_mismatch", "replacement_request_invalid", "replacement_scenario_invalid",
    "replacement_scenario_required", "replacement_service_proof_unavailable", "replacement_facts_not_found",
    "replacement_source_unavailable", "replacement_outcome_unknown", "replacement_internal_error",
]
_T = TypeVar("_T")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReplacementRootView(_StrictModel):
    kind: _RootKind
    root_id: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    current: bool
    caregiver_bound: bool


class ReplacementRootDeltaView(_StrictModel):
    retained: list[ReplacementRootView]
    superseded: list[ReplacementRootView]
    created: list[ReplacementRootView]

    @model_validator(mode="after")
    def validate_root_sets(self):
        groups = (self.retained, self.superseded, self.created)
        ids = [set(item.root_id for item in group) for group in groups]
        if any(len(group) != len(group_ids) for group, group_ids in zip(groups, ids)):
            raise ValueError("replacement_root_set_identity_not_unique")
        if ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2]:
            raise ValueError("replacement_root_delta_identity_overlap")
        cases = {item.case_no for group in groups for item in group}
        if len(cases) > 1:
            raise ValueError("replacement_root_case_mismatch")
        if any(
            [item.root_id for item in group] != sorted(item.root_id for item in group)
            for group in groups
        ):
            raise ValueError("replacement_root_set_not_canonical")
        return self


class ActualServiceProofView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    service_dates: list[date]
    source_identity: str = Field(min_length=1, max_length=191)
    source_version: StrictInt = Field(ge=0)
    fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_canonical_proof(self):
        dates = tuple(sorted(set(self.service_dates)))
        if tuple(self.service_dates) != dates:
            raise ValueError("actual_service_proof_dates_must_be_canonical")
        try:
            expected = AuthoritativeActualServiceProof(
                self.case_no,
                dates,
                self.source_identity,
                self.source_version,
                PreviewFingerprint(self.fingerprint),
            ).fingerprint
        except (TypeError, ValueError) as error:
            raise ValueError("actual_service_proof_fingerprint_mismatch") from error
        if expected is None or expected.value != self.fingerprint:
            raise ValueError("actual_service_proof_fingerprint_mismatch")
        return self


class CandidatePoolReuseProofView(_StrictModel):
    pool_identity: str = Field(min_length=1, max_length=191)
    round_identity: str = Field(min_length=1, max_length=191)
    coverage_version: StrictInt = Field(ge=0)
    availability_version: StrictInt = Field(ge=0)
    willingness_version: StrictInt = Field(ge=0)
    fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    same_round: bool
    coverage_valid: bool
    availability_valid: bool
    willingness_valid: bool
    fresh: bool
    accepted_candidate: bool
    case_no: str = Field(min_length=1, max_length=50)
    successor_round_identity: str = Field(min_length=1, max_length=191)
    generation_version: StrictInt = Field(ge=0)
    event_version: StrictInt = Field(ge=0)
    candidate_identity: str = Field(min_length=1, max_length=191)

    @model_validator(mode="after")
    def validate_reuse_proof(self):
        if self.round_identity != self.successor_round_identity:
            raise ValueError("candidate_pool_reuse_successor_round_mismatch")
        expected = fingerprint_payload(
            {
                "pool_identity": self.pool_identity,
                "round_identity": self.round_identity,
                "coverage_version": self.coverage_version,
                "availability_version": self.availability_version,
                "willingness_version": self.willingness_version,
                "same_round": self.same_round,
                "coverage_valid": self.coverage_valid,
                "availability_valid": self.availability_valid,
                "willingness_valid": self.willingness_valid,
                "fresh": self.fresh,
                "accepted_candidate": self.accepted_candidate,
                "case_no": self.case_no,
                "successor_round_identity": self.successor_round_identity,
                "generation_version": self.generation_version,
                "event_version": self.event_version,
                "candidate_identity": self.candidate_identity,
            }
        )
        if expected.value != self.fingerprint:
            raise ValueError("candidate_pool_reuse_fingerprint_mismatch")
        return self


class SuccessorRoundView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    round_identity: str = Field(min_length=1, max_length=191)
    generation_identity: str = Field(min_length=1, max_length=191)
    event_identity: str = Field(min_length=1, max_length=191)
    generation_version: StrictInt = Field(ge=0)
    event_version: StrictInt = Field(ge=0)
    candidate_count: StrictInt = Field(ge=0)
    zero_candidate_disposition: str | None = Field(default=None, max_length=500)
    fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_candidate_disposition(self):
        if self.candidate_count == 0 and not self.zero_candidate_disposition:
            raise ValueError("successor_round_zero_candidate_disposition_required")
        if self.candidate_count > 0 and self.zero_candidate_disposition is not None:
            raise ValueError("successor_round_zero_candidate_disposition_invalid")
        expected = fingerprint_payload(
            {
                "kind": "successor-round",
                "case_no": self.case_no,
                "round_identity": self.round_identity,
                "generation_identity": self.generation_identity,
                "event_identity": self.event_identity,
                "generation_version": self.generation_version,
                "event_version": self.event_version,
                "candidate_count": self.candidate_count,
                "zero_candidate_disposition": self.zero_candidate_disposition,
            }
        )
        if expected.value != self.fingerprint:
            raise ValueError("successor_round_fingerprint_mismatch")
        return self


class _ReplacementFactsView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    scenario: _Scenario
    outcome: _Outcome
    actual_service_day_count: StrictInt = Field(ge=0)
    actual_service_dates: list[date]
    actual_service_proof: ActualServiceProofView | None
    prior_generation_identity: str | None = Field(default=None, max_length=191)
    prior_event_identity: str | None = Field(default=None, max_length=191)
    prior_aggregate_identity: str | None = Field(default=None, max_length=191)
    generation_version: StrictInt = Field(ge=0)
    event_version: StrictInt = Field(ge=0)
    aggregate_version: StrictInt = Field(ge=0)
    impacted_roots: list[ReplacementRootView]
    retained_roots: list[ReplacementRootView]
    root_delta: ReplacementRootDeltaView | None
    candidate_pool_reuse_proof: CandidatePoolReuseProofView | None
    successor_round: SuccessorRoundView | None
    resume_step: _Step
    blockers: list[str]

    @model_validator(mode="after")
    def validate_case_and_service_count(self):
        canonical_dates = tuple(sorted(set(self.actual_service_dates)))
        if tuple(self.actual_service_dates) != canonical_dates:
            raise ValueError("actual_service_dates_must_be_canonical")
        if self.actual_service_day_count != len(canonical_dates):
            raise ValueError("actual_service_day_count_mismatch")
        roots = [*self.impacted_roots, *self.retained_roots]
        if any(
            [item.root_id for item in group] != sorted(item.root_id for item in group)
            for group in (self.impacted_roots, self.retained_roots)
        ):
            raise ValueError("replacement_root_set_not_canonical")
        if any(root.case_no != self.case_no for root in roots):
            raise ValueError("replacement_root_case_mismatch")
        impacted_ids = {root.root_id for root in self.impacted_roots}
        retained_ids = {root.root_id for root in self.retained_roots}
        if len(impacted_ids) != len(self.impacted_roots) or len(retained_ids) != len(self.retained_roots):
            raise ValueError("replacement_root_identity_not_unique")
        if impacted_ids & retained_ids:
            raise ValueError("replacement_root_delta_identity_overlap")
        if self.root_delta is not None:
            if any(
                root.case_no != self.case_no
                for group in (
                    self.root_delta.retained,
                    self.root_delta.superseded,
                    self.root_delta.created,
                )
                for root in group
            ):
                raise ValueError("replacement_root_case_mismatch")
            delta_ids = (
                tuple(root.root_id for root in self.root_delta.superseded),
                tuple(root.root_id for root in self.root_delta.retained),
                tuple(root.root_id for root in self.root_delta.created),
            )
            expected_ids = (
                tuple(root.root_id for root in self.impacted_roots),
                tuple(root.root_id for root in self.retained_roots),
                (),
            )
            if delta_ids[:2] != expected_ids[:2]:
                raise ValueError("replacement_root_delta_mismatch")
            if not hasattr(self, "created_roots") and delta_ids[2]:
                raise ValueError("replacement_root_delta_mismatch")
        if self.actual_service_day_count > 0 and self.actual_service_proof is None:
            raise ValueError("replacement_actual_service_requires_service_proof")
        if self.actual_service_proof is not None and self.actual_service_proof.case_no != self.case_no:
            raise ValueError("actual_service_proof_case_mismatch")
        if self.actual_service_proof is not None and tuple(self.actual_service_proof.service_dates) != canonical_dates:
            raise ValueError("actual_service_proof_dates_mismatch")
        if self.successor_round is not None and self.successor_round.case_no != self.case_no:
            raise ValueError("successor_round_case_mismatch")
        if self.successor_round is not None:
            successor = self.successor_round
            if successor.generation_version <= self.generation_version or successor.event_version <= self.event_version:
                raise ValueError("successor_round_version_mismatch")
            if successor.generation_identity == self.prior_generation_identity or successor.event_identity == self.prior_event_identity:
                raise ValueError("successor_round_identity_mismatch")
        if self.candidate_pool_reuse_proof is not None and self.candidate_pool_reuse_proof.case_no != self.case_no:
            raise ValueError("candidate_pool_reuse_case_mismatch")
        if self.candidate_pool_reuse_proof is not None:
            proof = self.candidate_pool_reuse_proof
            if (
                proof.generation_version != self.generation_version
                or proof.event_version != self.event_version
            ):
                raise ValueError("candidate_pool_reuse_version_mismatch")
            if self.successor_round is not None and proof.successor_round_identity != self.successor_round.round_identity:
                raise ValueError("candidate_pool_reuse_successor_round_mismatch")
        if self.outcome == "ready" and self.blockers:
            raise ValueError("replacement_ready_with_blocker")
        if self.actual_service_day_count and self.outcome != "substitution_referral":
            raise ValueError("replacement_actual_service_outcome_mismatch")
        if self.outcome == "ready":
            if self.actual_service_proof is None:
                raise ValueError("replacement_ready_requires_service_proof")
            if self.root_delta is None:
                raise ValueError("replacement_ready_requires_root_facts")
        if self.outcome == "substitution_referral":
            if self.root_delta is not None or self.impacted_roots or self.retained_roots:
                raise ValueError("replacement_referral_contains_replacement_facts")
            if self.candidate_pool_reuse_proof is not None or self.successor_round is not None:
                raise ValueError("replacement_referral_contains_successor_facts")
        return self

class ServiceBeforeReplacementQueryView(_ReplacementFactsView):
    pass


class ServiceBeforeReplacementPreviewView(_ReplacementFactsView):
    replacement_generation_identity: str | None = Field(default=None, max_length=191)
    replacement_event_identity: str | None = Field(default=None, max_length=191)
    successor_round_identity: str | None = Field(default=None, max_length=191)
    expected_generation_version: StrictInt = Field(ge=0)
    resulting_generation_version: StrictInt | None = Field(default=None, ge=0)
    expected_event_version: StrictInt = Field(ge=0)
    resulting_event_version: StrictInt | None = Field(default=None, ge=0)
    expected_aggregate_version: StrictInt = Field(ge=0)
    resulting_aggregate_version: StrictInt | None = Field(default=None, ge=0)
    superseded_roots: list[ReplacementRootView]
    created_roots: list[ReplacementRootView]
    preview_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    evidence: list[str]
    projection_kind: _Projection

    @model_validator(mode="after")
    def validate_replacement_facts(self):
        replacement_values = (
            self.replacement_generation_identity,
            self.replacement_event_identity,
            self.successor_round_identity,
            self.resulting_generation_version,
            self.resulting_event_version,
            self.resulting_aggregate_version,
        )
        if self.outcome == "ready":
            if any(
                value is None
                for value in (
                    self.prior_generation_identity,
                    self.prior_event_identity,
                    self.prior_aggregate_identity,
                )
            ):
                raise ValueError("replacement_ready_requires_prior_identities")
            if any(value is None for value in replacement_values):
                raise ValueError("replacement_ready_requires_replacement_facts")
            if not self.superseded_roots or not self.created_roots:
                raise ValueError("replacement_ready_requires_root_delta")
            if self.root_delta is None:
                raise ValueError("replacement_ready_requires_root_delta")
            if (
                tuple(item.root_id for item in self.root_delta.retained)
                != tuple(item.root_id for item in self.retained_roots)
                or tuple(item.root_id for item in self.root_delta.superseded)
                != tuple(item.root_id for item in self.superseded_roots)
                or tuple(item.root_id for item in self.root_delta.created)
                != tuple(item.root_id for item in self.created_roots)
            ):
                raise ValueError("replacement_root_delta_mismatch")
            if any(
                [item.root_id for item in group] != sorted(item.root_id for item in group)
                for group in (self.superseded_roots, self.created_roots)
            ):
                raise ValueError("replacement_root_set_not_canonical")
        if self.successor_round is not None:
            if self.successor_round_identity != self.successor_round.round_identity:
                raise ValueError("successor_round_identity_mismatch")
            if self.replacement_generation_identity is not None and self.successor_round.generation_identity != self.replacement_generation_identity:
                raise ValueError("successor_round_generation_identity_mismatch")
            if self.replacement_event_identity is not None and self.successor_round.event_identity != self.replacement_event_identity:
                raise ValueError("successor_round_event_identity_mismatch")
            if self.resulting_generation_version is not None and self.successor_round.generation_version != self.resulting_generation_version:
                raise ValueError("successor_round_generation_version_mismatch")
            if self.resulting_event_version is not None and self.successor_round.event_version != self.resulting_event_version:
                raise ValueError("successor_round_event_version_mismatch")
        if self.outcome == "substitution_referral":
            if any(value is not None for value in replacement_values):
                raise ValueError("replacement_referral_contains_replacement_facts")
            if (
                self.root_delta is not None
                or self.impacted_roots
                or self.retained_roots
                or self.superseded_roots
                or self.created_roots
                or self.candidate_pool_reuse_proof is not None
                or self.successor_round is not None
            ):
                raise ValueError("replacement_referral_contains_replacement_facts")
        return self


class ServiceBeforeReplacementPreviewBody(_StrictModel):
    scenario: _Scenario
    reason: str = Field(min_length=1, max_length=500)
    evidence: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_evidence(self):
        normalized = tuple(sorted(set(item.strip() for item in self.evidence if item.strip())))
        if not normalized or tuple(self.evidence) != normalized:
            raise ValueError("replacement_evidence_must_be_canonical")
        if self.reason != self.reason.strip():
            raise ValueError("replacement_reason_must_be_trimmed")
        return self


class ServiceBeforeReplacementApplyBody(ServiceBeforeReplacementPreviewBody):
    expected_generation_version: StrictInt = Field(ge=0)
    expected_event_version: StrictInt = Field(ge=0)
    expected_aggregate_version: StrictInt = Field(ge=0)
    prior_generation_identity: str = Field(min_length=1, max_length=191)
    prior_event_identity: str = Field(min_length=1, max_length=191)
    prior_aggregate_identity: str = Field(min_length=1, max_length=191)
    preview_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")


class ReplacementReceiptView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    receipt_identity: str = Field(min_length=1, max_length=191)
    idempotency_key: str = Field(min_length=1, max_length=191)
    command_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    replacement_generation_identity: str = Field(min_length=1, max_length=191)
    replacement_event_identity: str = Field(min_length=1, max_length=191)
    successor_round_identity: str = Field(min_length=1, max_length=191)
    resulting_generation_version: StrictInt = Field(ge=0)
    resulting_event_version: StrictInt = Field(ge=0)
    resulting_aggregate_version: StrictInt = Field(ge=0)
    outbox_identity: str = Field(min_length=1, max_length=191)
    retained_root_ids: list[str]
    superseded_root_ids: list[str]
    created_root_ids: list[str]
    retained_root_set_digest: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    retained_root_count: StrictInt = Field(ge=0)
    superseded_root_set_digest: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    superseded_root_count: StrictInt = Field(ge=0)
    created_root_set_digest: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    created_root_count: StrictInt = Field(ge=0)
    matching_package_lineage_id: StrictInt | None = Field(default=None, gt=0)
    matching_event_id: StrictInt | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_root_counts(self):
        for values, count in (
            (self.retained_root_ids, self.retained_root_count),
            (self.superseded_root_ids, self.superseded_root_count),
            (self.created_root_ids, self.created_root_count),
        ):
            if len(values) != count or len(values) != len(set(values)) or values != sorted(values):
                raise ValueError("replacement_root_count_mismatch")
        groups = (self.retained_root_ids, self.superseded_root_ids, self.created_root_ids)
        if len(set().union(*map(set, groups))) != sum(map(len, groups)):
            raise ValueError("replacement_root_delta_identity_overlap")
        return self


class ReplacementReadbackView(_StrictModel):
    case_no: str = Field(min_length=1, max_length=50)
    generation_identity: str = Field(min_length=1, max_length=191)
    event_identity: str = Field(min_length=1, max_length=191)
    successor_round_identity: str = Field(min_length=1, max_length=191)
    generation_version: StrictInt = Field(ge=0)
    event_version: StrictInt = Field(ge=0)
    aggregate_version: StrictInt = Field(ge=0)
    retained_root_ids: list[str]
    superseded_root_ids: list[str]
    created_root_ids: list[str]
    root_set_digests: list[_Fingerprint] = Field(min_length=3, max_length=3)
    root_set_counts: list[StrictInt] = Field(min_length=3, max_length=3)
    outbox_identity: str = Field(min_length=1, max_length=191)
    matching_package_lineage_id: StrictInt | None = Field(default=None, gt=0)
    matching_event_id: StrictInt | None = Field(default=None, gt=0)
    complete: bool

    @model_validator(mode="after")
    def validate_readback_root_counts(self):
        groups = (self.retained_root_ids, self.superseded_root_ids, self.created_root_ids)
        if any(values != sorted(set(values)) for values in groups):
            raise ValueError("replacement_root_set_not_canonical")
        if list(self.root_set_counts) != [len(values) for values in groups]:
            raise ValueError("replacement_root_count_mismatch")
        if len(set().union(*map(set, groups))) != sum(map(len, groups)):
            raise ValueError("replacement_root_delta_identity_overlap")
        return self


class ServiceBeforeReplacementApplyView(_StrictModel):
    status: Literal["applied", "replayed"]
    receipt: ReplacementReceiptView
    readback: ReplacementReadbackView

    @model_validator(mode="after")
    def validate_complete_exact_readback(self):
        receipt = self.receipt
        readback = self.readback
        if not readback.complete:
            raise ValueError("replacement_apply_readback_incomplete")
        if receipt.case_no != readback.case_no:
            raise ValueError("replacement_apply_case_mismatch")
        if (
            receipt.replacement_generation_identity != readback.generation_identity
            or receipt.replacement_event_identity != readback.event_identity
            or receipt.successor_round_identity != readback.successor_round_identity
            or receipt.resulting_generation_version != readback.generation_version
            or receipt.resulting_event_version != readback.event_version
            or receipt.resulting_aggregate_version != readback.aggregate_version
            or receipt.outbox_identity != readback.outbox_identity
            or receipt.matching_package_lineage_id != readback.matching_package_lineage_id
            or receipt.matching_event_id != readback.matching_event_id
        ):
            raise ValueError("replacement_apply_readback_identity_mismatch")
        receipt_groups = (
            receipt.retained_root_ids,
            receipt.superseded_root_ids,
            receipt.created_root_ids,
        )
        readback_groups = (
            readback.retained_root_ids,
            readback.superseded_root_ids,
            readback.created_root_ids,
        )
        if receipt_groups != readback_groups:
            raise ValueError("replacement_apply_readback_roots_mismatch")
        expected_digests = [_root_set_digest(values) for values in receipt_groups]
        expected_counts = [len(values) for values in receipt_groups]
        if (
            readback.root_set_digests != expected_digests
            or readback.root_set_counts != expected_counts
            or [
                receipt.retained_root_set_digest,
                receipt.superseded_root_set_digest,
                receipt.created_root_set_digest,
            ] != expected_digests
            or [
                receipt.retained_root_count,
                receipt.superseded_root_count,
                receipt.created_root_count,
            ] != expected_counts
        ):
            raise ValueError("replacement_apply_readback_root_digest_mismatch")
        return self


class ServiceBeforeReplacementTypedErrorView(_StrictModel):
    category: _ErrorCategory
    code: _ErrorCode
    message: str
    field_errors: list["ServiceBeforeReplacementFieldErrorView"] = Field(default_factory=list)
    domain_blockers: list[str] = Field(default_factory=list)
    retryable: bool = False
    correlation_id: str
    current_version: StrictInt | None = None


class ServiceBeforeReplacementFieldErrorView(_StrictModel):
    field: str = Field(min_length=1, max_length=191)
    code: str = Field(min_length=1, max_length=191)
    message: str = Field(min_length=1, max_length=500)


class ServiceBeforeReplacementResponse(BaseModel, Generic[_T]):
    """RPRE-local strict success envelope; the Global BaseResponse stays unchanged."""

    model_config = ConfigDict(extra="forbid", strict=True)

    success: Literal[True] = True
    message: str = Field(min_length=1, max_length=500)
    data: _T
    error: None = None


def _root_set_digest(values: list[str]) -> str:
    return sha256("\n".join(values).encode("utf-8")).hexdigest()


__all__ = [
    "ActualServiceProofView", "CandidatePoolReuseProofView", "ReplacementReadbackView",
    "ReplacementReceiptView", "ReplacementRootDeltaView", "ReplacementRootView",
    "ServiceBeforeReplacementApplyBody", "ServiceBeforeReplacementApplyView",
    "ServiceBeforeReplacementPreviewBody", "ServiceBeforeReplacementPreviewView",
    "ServiceBeforeReplacementQueryView", "ServiceBeforeReplacementTypedErrorView",
    "ServiceBeforeReplacementFieldErrorView", "ServiceBeforeReplacementResponse",
    "SuccessorRoundView",
]

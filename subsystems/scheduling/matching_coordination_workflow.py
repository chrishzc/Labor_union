"""
File: matching_coordination_workflow.py
Description: 提供 M3 coordination 的 Query／Preview／Apply 與日期變更結果投影。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, Sequence

from domains.scheduling.staff_availability import StaffAvailabilityFacts

from domains.scheduling.matching_coordination import (
    MatchingCandidateResult,
    MatchingCriteriaSnapshot,
    MatchingDecisionLineage,
    MatchingDomainError,
    MatchingCrossDomainRequest,
    MatchingPackage,
    MatchingPackageState,
    MatchingSourceTuple,
    MatchingSourceVersion,
    DynamicWillingnessLineage,
    RefusalHistoryEntry,
    RefusalRouting,
    ZeroCandidateDecision,
    ZeroCandidateAlternative,
    build_criteria_diff,
    build_manual_matching_package,
    build_cross_domain_request,
    build_willingness_lineage,
    build_zero_candidate_decision,
    build_zero_candidate_alternative,
    canonical_source_tuple,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyCaregiverSelection,
    ApplyCriteriaDiffResend,
    ApplyCustomerMatchingDecision,
    ApplyInitialCriteriaSnapshot,
    ApplyLeaveImpactOnMatching,
    ApplyRematch,
    ApplyServiceDateChangeRematch,
    ApplyZeroCandidateAlternative,
    ApplyZeroCandidateConfirmation,
    CriteriaDiffView,
    MatchingApplyReceipt,
    MatchingCommand,
    MatchingCommandName,
    MatchingDecisionView,
    MatchingCriteriaRecontactIntentProjection,
    MatchingNotificationIntentProjection,
    MatchingNotificationRecipientRole,
    MatchingPackageView,
    PreviewCriteriaDiffResend,
    PreviewLeaveImpactOnMatching,
    PreviewMatchingPackage,
    PreviewRematch,
    PreviewServiceDateChangeRematch,
    PreviewZeroCandidateAlternative,
    PreviewZeroCandidateConfirmation,
    QueryMatchingCoordination,
    ZeroCandidateAlternativeView,
    alternative_view,
    command_fingerprint,
    criteria_diff_view,
    decision_view,
    package_view,
)


class MatchingCoordinationWorkflowError(Exception):
    """框架無關的 typed workflow failure。"""

    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True, slots=True)
class MatchingCoordinationFacts:
    snapshot: MatchingCriteriaSnapshot
    package: MatchingPackage | None
    candidates: tuple[MatchingCandidateResult, ...] = ()
    source_versions: MatchingSourceTuple = ()
    criteria_snapshots: tuple[MatchingCriteriaSnapshot, ...] = ()
    refusal_history: tuple[RefusalHistoryEntry, ...] = ()
    willingness_lineage: tuple[DynamicWillingnessLineage, ...] = ()

    def __post_init__(self) -> None:
        source_versions = self.source_versions or self.snapshot.source_versions
        object.__setattr__(self, "source_versions", canonical_source_tuple(source_versions))
        if not isinstance(self.candidates, tuple):
            raise TypeError("matching facts candidates must be a tuple")
        if not isinstance(self.criteria_snapshots, tuple) or any(not isinstance(item, MatchingCriteriaSnapshot) for item in self.criteria_snapshots):
            raise TypeError("matching facts criteria snapshots must be a typed tuple")
        if not isinstance(self.refusal_history, tuple) or any(not isinstance(item, RefusalHistoryEntry) for item in self.refusal_history):
            raise TypeError("matching facts refusal history must be a typed tuple")
        if not isinstance(self.willingness_lineage, tuple) or any(not isinstance(item, DynamicWillingnessLineage) for item in self.willingness_lineage):
            raise TypeError("matching facts willingness lineage must be a typed tuple")


class MatchingCoordinationReadPort(Protocol):
    """後續 Phase B 可實作的 typed read port；Phase A 不依賴 concrete adapter。"""

    def load(self, case_no: str) -> MatchingCoordinationFacts: ...


@dataclass(frozen=True, slots=True)
class ServiceDateShiftAvailabilityConfirmation:
    """Owner facts confirm the incumbent remains available after a date shift."""

    intent_id: str
    case_no: str
    assignment_id: int
    staff_id: int
    original_service_dates: tuple[date, ...]
    shifted_service_dates: tuple[date, ...]
    source_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ServiceDateShiftReassignmentReference:
    """Typed rematch queue reference when owner availability facts conflict."""

    queue_reference: str
    case_no: str
    assignment_id: int
    staff_id: int
    shifted_service_dates: tuple[date, ...]
    conflict_source_ids: tuple[str, ...]
    source_fingerprint: PreviewFingerprint


class MatchingCoordinationWorkflow:
    """純 coordination foundation；不取得 clock、DB、network 或 provider。"""

    def __init__(self, read_port: MatchingCoordinationReadPort | None = None) -> None:
        self._read_port = read_port

    def evaluate_service_date_shift(
        self,
        *,
        case_no: str,
        assignment_id: int,
        original_staff_id: int,
        original_service_dates: tuple[date, ...],
        shifted_service_dates: tuple[date, ...],
        availability: StaffAvailabilityFacts,
    ) -> ServiceDateShiftAvailabilityConfirmation | ServiceDateShiftReassignmentReference:
        """Project an owner-fact date-shift outcome without changing any root fact."""

        if not isinstance(case_no, str) or not case_no.strip():
            raise TypeError("case_no must be canonical text")
        if type(assignment_id) is not int or assignment_id <= 0:
            raise TypeError("assignment_id must be positive int")
        if type(original_staff_id) is not int or original_staff_id <= 0:
            raise TypeError("original_staff_id must be positive int")
        if not isinstance(availability, StaffAvailabilityFacts):
            raise TypeError("availability must be StaffAvailabilityFacts")
        if availability.staff_id != original_staff_id or availability.target_block is not None:
            raise ValueError("availability facts do not match incumbent")
        _validate_shift_dates(original_service_dates, "original_service_dates")
        _validate_shift_dates(shifted_service_dates, "shifted_service_dates")
        if original_service_dates == shifted_service_dates:
            raise ValueError("shifted_service_dates must differ from original dates")

        payload = {
            "case_no": case_no,
            "assignment_id": assignment_id,
            "staff_id": original_staff_id,
            "original_service_dates": tuple(item.isoformat() for item in original_service_dates),
            "shifted_service_dates": tuple(item.isoformat() for item in shifted_service_dates),
            "availability_version": availability.aggregate_version,
            "blocks": tuple(
                (item.block_id, item.kind.value, item.start_date.isoformat(), item.end_date.isoformat() if item.end_date else None, item.status.value, item.reason)
                for item in availability.blocks
            ),
            "conflicts": tuple(
                (item.source_kind, item.source_identity, item.start_date.isoformat(), item.end_date.isoformat())
                for item in availability.conflicts
            ),
        }
        source_fingerprint = fingerprint_payload(payload)
        blocked_sources = tuple(sorted({
            *(f"availability:block:{item.block_id}" for item in availability.blocks if item.status.value == "effective" and _dates_overlap(shifted_service_dates, item.start_date, item.end_date)),
            *(f"{item.source_kind}:{item.source_identity}" for item in availability.conflicts if _dates_overlap(shifted_service_dates, item.start_date, item.end_date)),
        }))
        if blocked_sources:
            return ServiceDateShiftReassignmentReference(
                queue_reference=f"matching:{case_no}:service-date-reassignment:{assignment_id}:{source_fingerprint.value}",
                case_no=case_no,
                assignment_id=assignment_id,
                staff_id=original_staff_id,
                shifted_service_dates=shifted_service_dates,
                conflict_source_ids=blocked_sources,
                source_fingerprint=source_fingerprint,
            )
        return ServiceDateShiftAvailabilityConfirmation(
            intent_id=f"matching:{case_no}:service-date-approval:{assignment_id}:{source_fingerprint.value}",
            case_no=case_no,
            assignment_id=assignment_id,
            staff_id=original_staff_id,
            original_service_dates=original_service_dates,
            shifted_service_dates=shifted_service_dates,
            source_fingerprint=source_fingerprint,
        )

    def preview_service_date_shift(
        self,
        request: PreviewServiceDateChangeRematch,
        facts: MatchingCoordinationFacts,
        availability: StaffAvailabilityFacts,
    ) -> ServiceDateShiftAvailabilityConfirmation | ServiceDateShiftReassignmentReference:
        """Validate current M3 context before projecting an owner-supplied date shift."""

        _validate_source_versions(
            request.expected_source_versions,
            facts.source_versions,
            request.correlation_id,
        )
        if request.criteria_snapshot_id != facts.snapshot.snapshot_id:
            raise _workflow_error(
                request.correlation_id, "matching_service_date_conflict"
            )
        if request.package_id is not None:
            if facts.package is None or request.package_id != facts.package.package_id:
                raise _workflow_error(request.correlation_id, "matching_package_stale")
            if facts.package.criteria_snapshot_id != request.criteria_snapshot_id:
                raise _workflow_error(
                    request.correlation_id, "matching_service_date_conflict"
                )
        return self.evaluate_service_date_shift(
            case_no=request.case_no,
            assignment_id=request.assignment_id,
            original_staff_id=request.original_staff_id,
            original_service_dates=request.original_service_dates,
            shifted_service_dates=request.shifted_service_dates,
            availability=availability,
        )

    def query(self, request: QueryMatchingCoordination | str, facts: MatchingCoordinationFacts | None = None) -> MatchingPackageView | None:
        facts = self._facts(request, facts)
        return package_view(facts.package) if facts.package is not None else None

    def preview(
        self,
        request: MatchingCommand,
        facts: MatchingCoordinationFacts,
    ) -> MatchingPackageView | CriteriaDiffView | ZeroCandidateAlternativeView:
        _validate_source_versions(request.expected_source_versions, facts.source_versions, request.correlation_id)
        if isinstance(request, PreviewMatchingPackage):
            if request.criteria_snapshot_id != facts.snapshot.snapshot_id:
                raise _workflow_error(request.correlation_id, "matching_package_stale")
            if not request.segments:
                if facts.package is None:
                    raise _workflow_error(request.correlation_id, "matching_package_not_found")
                return package_view(facts.package)
            selection_fingerprint = fingerprint_payload(
                {
                    "case_no": request.case_no,
                    "criteria_snapshot_id": request.criteria_snapshot_id,
                    "required_service_dates": tuple(
                        item.isoformat() for item in request.required_service_dates
                    ),
                    "segments": tuple(
                        (
                            item.staff_id,
                            item.sequence,
                            tuple(day.isoformat() for day in item.service_dates),
                        )
                        for item in request.segments
                    ),
                    "source_versions": tuple(
                        item.as_payload() for item in facts.source_versions
                    ),
                }
            )
            package = build_manual_matching_package(
                package_id=f"matching:{request.case_no}:package:{selection_fingerprint.value[:24]}",
                version=1 if facts.package is None else facts.package.version + 1,
                segments=request.segments,
                required_service_dates=request.required_service_dates,
                candidate_results=facts.candidates,
                criteria_snapshot_id=request.criteria_snapshot_id,
                source_versions=facts.source_versions,
            )
            return package_view(package)
        if isinstance(request, (PreviewRematch, PreviewServiceDateChangeRematch, PreviewLeaveImpactOnMatching)):
            if facts.package is None:
                raise _workflow_error(request.correlation_id, "matching_package_not_found")
            return package_view(facts.package)
        if isinstance(request, PreviewCriteriaDiffResend):
            snapshots = {item.snapshot_id: item for item in facts.criteria_snapshots}
            snapshots.setdefault(facts.snapshot.snapshot_id, facts.snapshot)
            before = snapshots.get(request.before_snapshot_id)
            after = snapshots.get(request.after_snapshot_id)
            if before is None or after is None:
                raise _workflow_error(request.correlation_id, "matching_criteria_diff_required")
            return criteria_diff_view(build_criteria_diff(before, after, facts.candidates, facts.refusal_history, facts.willingness_lineage))
        if isinstance(request, PreviewZeroCandidateAlternative):
            if request.criteria_snapshot_id != facts.snapshot.snapshot_id:
                raise _workflow_error(request.correlation_id, "matching_alternative_stale")
            if any(
                item.eligibility.value == "eligible" and item.willingness == "willing"
                for item in facts.candidates
            ):
                raise _workflow_error(request.correlation_id, "matching_no_candidate")
            relaxed = tuple(request.relaxed_criteria)
            if not relaxed or not set(relaxed).issubset(facts.snapshot.criteria):
                raise _workflow_error(request.correlation_id, "matching_alternative_not_explicit")
            unchanged = tuple(sorted(set(facts.snapshot.criteria) - set(relaxed)))
            selection_fingerprint = fingerprint_payload(
                {
                    "snapshot_id": facts.snapshot.snapshot_id,
                    "policy_id": request.policy_id,
                    "policy_version": request.policy_version,
                    "relaxed_criteria": relaxed,
                }
            )
            alternative = build_zero_candidate_alternative(
                alternative_id=(
                    f"{facts.snapshot.snapshot_id}:alternative:"
                    f"{selection_fingerprint.value[:24]}"
                ),
                policy_id=request.policy_id,
                policy_version=request.policy_version,
                relaxed_criteria=relaxed,
                unchanged_hard_criteria=unchanged,
                candidate_result=None,
                risk_warnings=("explicit_manual_confirmation_required",),
            )
            return alternative_view(alternative)
        if isinstance(request, PreviewZeroCandidateConfirmation):
            return package_view(_zero_candidate_confirmation_package(request, facts))
        raise _workflow_error(request.correlation_id, "matching_criteria_invalid")

    def preview_matching_package(self, package: MatchingPackage) -> MatchingPackageView:
        return package_view(package)

    def preview_criteria_diff(
        self,
        before: MatchingCriteriaSnapshot,
        after: MatchingCriteriaSnapshot,
        candidates: Sequence[MatchingCandidateResult] = (),
        refusal_history: Sequence[RefusalHistoryEntry] = (),
    ) -> CriteriaDiffView:
        return criteria_diff_view(build_criteria_diff(before, after, candidates, refusal_history))

    def route_refusals(
        self,
        before: MatchingCriteriaSnapshot,
        after: MatchingCriteriaSnapshot,
        refusal_history: Sequence[RefusalHistoryEntry],
    ) -> tuple[RefusalRouting, ...]:
        return build_criteria_diff(before, after, refusal_history=refusal_history).refusal_routes

    def refresh_willingness(
        self,
        *,
        candidate_id: str,
        staff_id: int,
        snapshot: MatchingCriteriaSnapshot,
        previous_state: str,
        current_state: str,
        event_id: str,
        reason_code: str | None = None,
        affected_criteria: tuple[str, ...] = (),
    ) -> DynamicWillingnessLineage:
        """Create an append-only current-snapshot observation; no root write."""

        return build_willingness_lineage(event_id=event_id, candidate_id=candidate_id, staff_id=staff_id, snapshot=snapshot, previous_state=previous_state, current_state=current_state, reason_code=reason_code, affected_criteria=affected_criteria)

    def preview_zero_candidate_alternative(
        self,
        *,
        alternative_id: str,
        policy_id: str,
        policy_version: int,
        relaxed_criteria: Sequence[str],
        unchanged_hard_criteria: Sequence[str],
        candidate_result: MatchingCandidateResult | None = None,
        risk_warnings: Sequence[str] = (),
    ) -> ZeroCandidateAlternativeView:
        return alternative_view(build_zero_candidate_alternative(alternative_id=alternative_id, policy_id=policy_id, policy_version=policy_version, relaxed_criteria=relaxed_criteria, unchanged_hard_criteria=unchanged_hard_criteria, candidate_result=candidate_result, risk_warnings=risk_warnings))

    def apply(
        self,
        request: MatchingCommand,
        facts: MatchingCoordinationFacts,
        *,
        preview_fingerprint: PreviewFingerprint,
        fresh_effects_match: bool = True,
    ) -> MatchingApplyReceipt:
        _validate_source_versions(request.expected_source_versions, facts.source_versions, request.correlation_id)
        if not isinstance(preview_fingerprint, PreviewFingerprint):
            raise TypeError("preview_fingerprint must be PreviewFingerprint")
        request_preview = getattr(request, "preview_fingerprint", None)
        if request_preview is not None and request_preview != preview_fingerprint:
            raise _workflow_error(request.correlation_id, "matching_invalid_replay_snapshot")
        if isinstance(request, ApplyInitialCriteriaSnapshot):
            if request.preview_fingerprint != facts.snapshot.fingerprint:
                raise _workflow_error(
                    request.correlation_id, "matching_invalid_replay_snapshot"
                )
            return self._receipt(
                request,
                facts,
                preview_fingerprint,
                result_state="criteria_snapshotted",
            )
        if isinstance(request, ApplyCustomerMatchingDecision):
            if facts.package is None:
                raise _workflow_error(request.correlation_id, "matching_package_not_found")
            if request.package_id != facts.package.package_id or request.package_version != facts.package.version:
                raise _workflow_error(request.correlation_id, "matching_package_stale")
            if request.criteria_snapshot_id != facts.package.criteria_snapshot_id:
                raise _workflow_error(request.correlation_id, "matching_package_stale")
            if request.preview_fingerprint != facts.package.fingerprint:
                raise _workflow_error(request.correlation_id, "matching_invalid_replay_snapshot")
            if request.decision not in {"accepted", "rejected", "disagree"}:
                raise _workflow_error(request.correlation_id, "matching_customer_decision_conflict")
            if request.candidate_id is not None and not any(item.candidate_id == request.candidate_id for item in facts.candidates):
                raise _workflow_error(request.correlation_id, "matching_candidate_not_found")
            if request.decision == "accepted":
                _require_willing_candidate(request, facts, require_willing=fresh_effects_match)
            if request.decision == "accepted" and not fresh_effects_match:
                state = "rematch_required"
            else:
                state = "accepted" if request.decision == "accepted" else request.decision
            cross_request = None
            if request.decision == "accepted":
                if facts.package is None:
                    raise _workflow_error(request.correlation_id, "matching_package_not_found")
                cross_request = build_cross_domain_request(
                    request_id=f"{request.idempotency_key.value}:conversion" if fresh_effects_match else f"{request.idempotency_key.value}:rematch",
                    request_kind="assignment_conversion_requested" if fresh_effects_match else "rematch_requested",
                    case_no=request.case_no,
                    package=facts.package,
                    criteria_snapshot_id=request.criteria_snapshot_id,
                    candidate_id=request.candidate_id,
                    source_versions=facts.source_versions,
                    lineage_event_id=f"{request.idempotency_key.value}:decision",
                    reason=request.reason,
                )
            return self._receipt(request, facts, preview_fingerprint, result_state=state, candidate_id=request.candidate_id, cross_domain_request=cross_request)
        if isinstance(request, ApplyCaregiverSelection):
            if (
                facts.package is None
                or request.package_id != facts.package.package_id
                or request.package_version != facts.package.version
                or request.criteria_snapshot_id != facts.package.criteria_snapshot_id
            ):
                raise _workflow_error(request.correlation_id, "matching_package_stale")
            if request.preview_fingerprint != facts.package.fingerprint:
                raise _workflow_error(request.correlation_id, "matching_invalid_replay_snapshot")
            candidate = next((item for item in facts.candidates if item.candidate_id == request.candidate_id), None)
            if candidate is None:
                raise _workflow_error(request.correlation_id, "matching_candidate_not_found")
            if request.willingness == "willing":
                if request.reason_code is not None or request.affected_criteria:
                    raise _workflow_error(request.correlation_id, "matching_willingness_conflict")
                affected_criteria = tuple(sorted(facts.snapshot.criteria))
            elif request.willingness == "unwilling":
                if (
                    request.reason_code is None
                    or not request.affected_criteria
                    or not set(request.affected_criteria).issubset(facts.snapshot.criteria)
                ):
                    raise _workflow_error(request.correlation_id, "matching_willingness_conflict")
                affected_criteria = request.affected_criteria
            else:
                raise _workflow_error(request.correlation_id, "matching_willingness_conflict")
            lineage = build_willingness_lineage(event_id=f"{request.idempotency_key.value}:willingness", candidate_id=request.candidate_id, staff_id=candidate.staff_id, snapshot=facts.snapshot, previous_state=candidate.willingness, current_state=request.willingness, reason_code=request.reason_code, affected_criteria=affected_criteria)
            return self._receipt(request, facts, preview_fingerprint, result_state=request.willingness, candidate_id=request.candidate_id, willingness_lineage=lineage)
        if isinstance(request, ApplyServiceDateChangeRematch):
            if request.criteria_snapshot_id != facts.snapshot.snapshot_id:
                raise _workflow_error(
                    request.correlation_id, "matching_service_date_conflict"
                )
            if request.package_id is not None:
                if (
                    facts.package is None
                    or request.package_id != facts.package.package_id
                    or facts.package.criteria_snapshot_id != request.criteria_snapshot_id
                ):
                    raise _workflow_error(
                        request.correlation_id, "matching_package_stale"
                    )
            return self._receipt(
                request,
                facts,
                preview_fingerprint,
                result_state="rematch_required",
            )
        if isinstance(request, ApplyLeaveImpactOnMatching):
            if (
                facts.package is None
                or request.package_id != facts.package.package_id
                or request.criteria_snapshot_id != facts.snapshot.snapshot_id
                or facts.package.criteria_snapshot_id != request.criteria_snapshot_id
            ):
                raise _workflow_error(
                    request.correlation_id, "matching_package_stale"
                )
            return self._receipt(
                request,
                facts,
                preview_fingerprint,
                result_state="rematch_required",
            )
        if isinstance(request, ApplyRematch):
            if facts.package is None:
                raise _workflow_error(request.correlation_id, "matching_package_not_found")
            requested_package = getattr(request, "package_id", None)
            if requested_package is not None and requested_package != facts.package.package_id:
                raise _workflow_error(request.correlation_id, "matching_package_stale")
            if request.preview_fingerprint != facts.package.fingerprint:
                raise _workflow_error(request.correlation_id, "matching_invalid_replay_snapshot")
            return self._receipt(request, facts, preview_fingerprint, result_state="rematch_required")
        if isinstance(request, ApplyCriteriaDiffResend):
            snapshots = {item.snapshot_id: item for item in facts.criteria_snapshots}
            snapshots.setdefault(facts.snapshot.snapshot_id, facts.snapshot)
            before = snapshots.get(request.before_snapshot_id)
            after = snapshots.get(request.after_snapshot_id)
            if before is None or after is None:
                raise _workflow_error(
                    request.correlation_id,
                    "matching_criteria_diff_required",
                )
            diff = build_criteria_diff(
                before,
                after,
                facts.candidates,
                facts.refusal_history,
                facts.willingness_lineage,
            )
            if request.preview_fingerprint != diff.fingerprint:
                raise _workflow_error(
                    request.correlation_id,
                    "matching_recontact_source_stale",
                )
            recipient_ids = request.recipient_ids
            if (
                not recipient_ids
                or any(not isinstance(item, str) for item in recipient_ids)
                or tuple(sorted(set(recipient_ids))) != recipient_ids
                or any(item not in diff.affected_recipient_ids for item in recipient_ids)
            ):
                raise _workflow_error(
                    request.correlation_id,
                    "matching_recontact_source_stale",
                )
            outbox_intent_ids = tuple(
                f"{request.idempotency_key.value}:criteria-resend:{recipient_id}"
                for recipient_id in recipient_ids
            )
            route_by_candidate = {
                item.candidate_id: item for item in diff.refusal_routes
            }
            candidate_by_id = {
                item.candidate_id: item for item in facts.candidates
            }
            package = facts.package
            recontact_intents = tuple(
                MatchingCriteriaRecontactIntentProjection(
                    intent_id=intent_id,
                    recipient_subject_reference=(
                        f"staff:{candidate_by_id[recipient_id].staff_id}"
                    ),
                    candidate_id=recipient_id,
                    staff_id=candidate_by_id[recipient_id].staff_id,
                    route_group=route_by_candidate[recipient_id].group,
                    action=route_by_candidate[recipient_id].action,
                    reason_code=route_by_candidate[recipient_id].reason_code,
                    before_snapshot_id=before.snapshot_id,
                    after_snapshot_id=after.snapshot_id,
                    diff_fingerprint=diff.fingerprint,
                    source_versions=facts.source_versions,
                    idempotency_key=request.idempotency_key,
                    package_id=package.package_id if package is not None else None,
                    package_version=package.version if package is not None else None,
                    package_fingerprint=(
                        package.fingerprint if package is not None else None
                    ),
                )
                for recipient_id, intent_id in zip(
                    recipient_ids, outbox_intent_ids, strict=True
                )
            )
            return self._receipt(
                request,
                facts,
                preview_fingerprint,
                result_state="intent_queued",
                outbox_intent_ids=outbox_intent_ids,
                criteria_recontact_intents=recontact_intents,
            )
        if isinstance(request, ApplyZeroCandidateAlternative):
            if request.criteria_snapshot_id != facts.snapshot.snapshot_id:
                raise _workflow_error(request.correlation_id, "matching_alternative_stale")
            if any(
                item.eligibility.value == "eligible" and item.willingness == "willing"
                for item in facts.candidates
            ):
                raise _workflow_error(request.correlation_id, "matching_no_candidate")
            relaxed = tuple(request.relaxed_criteria)
            if not set(relaxed).issubset(facts.snapshot.criteria):
                raise _workflow_error(
                    request.correlation_id, "matching_alternative_not_explicit"
                )
            selection_fingerprint = fingerprint_payload(
                {
                    "snapshot_id": facts.snapshot.snapshot_id,
                    "policy_id": request.policy_id,
                    "policy_version": request.policy_version,
                    "relaxed_criteria": relaxed,
                }
            )
            expected_alternative_id = (
                f"{facts.snapshot.snapshot_id}:alternative:"
                f"{selection_fingerprint.value[:24]}"
            )
            if request.alternative_id != expected_alternative_id:
                raise _workflow_error(request.correlation_id, "matching_alternative_stale")
            alternative = build_zero_candidate_alternative(
                alternative_id=expected_alternative_id,
                policy_id=request.policy_id,
                policy_version=request.policy_version,
                relaxed_criteria=relaxed,
                unchanged_hard_criteria=tuple(
                    sorted(set(facts.snapshot.criteria) - set(relaxed))
                ),
                risk_warnings=("explicit_manual_confirmation_required",),
            )
            if request.preview_fingerprint != alternative.preview_fingerprint:
                raise _workflow_error(request.correlation_id, "matching_alternative_stale")
            lineage = build_zero_candidate_decision(event_id=f"{request.idempotency_key.value}:zero-candidate", case_no=request.case_no, alternative=alternative, decision=request.decision, actor_id=request.actor.actor_id, source_versions=facts.source_versions)
            state = "alternative_agreed_pending_owning_workflows" if lineage.decision is ZeroCandidateDecision.AGREE else "awaiting_matching"
            return self._receipt(request, facts, preview_fingerprint, result_state=state, zero_candidate_decision=lineage)
        if isinstance(request, ApplyZeroCandidateConfirmation):
            package = _zero_candidate_confirmation_package(request, facts)
            if request.preview_fingerprint != package.fingerprint:
                raise _workflow_error(
                    request.correlation_id,
                    "matching_zero_candidate_confirmation_stale",
                )
            event_id = f"{request.idempotency_key.value}:zero-candidate-confirmed"
            return self._receipt(
                request,
                facts,
                preview_fingerprint,
                result_state="zero_candidate_confirmed",
                outbox_intent_ids=(f"{event_id}:assignment",),
                resulting_package=package,
            )
        raise _workflow_error(request.correlation_id, "matching_criteria_invalid")

    def apply_customer_decision(self, request: ApplyCustomerMatchingDecision, facts: MatchingCoordinationFacts, *, fresh_effects_match: bool = True) -> MatchingDecisionView:
        _validate_source_versions(request.expected_source_versions, facts.source_versions, request.correlation_id)
        if facts.package is None or facts.package.package_id != request.package_id:
            raise _workflow_error(request.correlation_id, "matching_package_stale")
        if request.decision not in {"accepted", "rejected", "disagree"}:
            raise _workflow_error(request.correlation_id, "matching_customer_decision_conflict")
        if request.package_version != facts.package.version:
            raise _workflow_error(request.correlation_id, "matching_package_stale")
        if request.candidate_id is not None and not any(
            item.candidate_id == request.candidate_id for item in facts.candidates
        ):
            raise _workflow_error(request.correlation_id, "matching_candidate_not_found")
        if request.decision == "accepted":
            _require_willing_candidate(request, facts, require_willing=fresh_effects_match)
        effects = "conversion_reference_requested" if request.decision == "accepted" and fresh_effects_match else ("rematch_required" if request.decision == "accepted" else request.decision)
        conversion_request = None
        if request.decision == "accepted":
            conversion_request = build_cross_domain_request(
                request_id=f"{request.idempotency_key.value}:conversion" if fresh_effects_match else f"{request.idempotency_key.value}:rematch",
                request_kind="assignment_conversion_requested" if fresh_effects_match else "rematch_requested",
                case_no=request.case_no,
                package=facts.package,
                criteria_snapshot_id=request.criteria_snapshot_id,
                candidate_id=request.candidate_id,
                source_versions=facts.source_versions,
                lineage_event_id=f"{request.idempotency_key.value}:decision",
                reason=request.reason,
            )
        lineage = MatchingDecisionLineage(
            event_id=f"{request.idempotency_key.value}:decision",
            case_no=request.case_no,
            package_id=request.package_id,
            package_version=request.package_version,
            candidate_id=request.candidate_id,
            actor_id=request.actor.actor_id,
            customer_state=request.decision,
            caregiver_state="unchanged",
            fresh_effects_status=effects,
            rematch_reference=None if effects != "rematch_required" else f"{request.idempotency_key.value}:rematch",
            source_versions=facts.source_versions,
            conversion_request=conversion_request,
        )
        return decision_view(lineage)

    def _receipt(
        self,
        request: MatchingCommand,
        facts: MatchingCoordinationFacts,
        preview: PreviewFingerprint,
        *,
        result_state: str,
        candidate_id: str | None = None,
        cross_domain_request: MatchingCrossDomainRequest | None = None,
        zero_candidate_decision=None,
        willingness_lineage: DynamicWillingnessLineage | None = None,
        outbox_intent_ids: tuple[str, ...] = (),
        criteria_recontact_intents: tuple[
            MatchingCriteriaRecontactIntentProjection, ...
        ] = (),
        resulting_package: MatchingPackage | None = None,
    ) -> MatchingApplyReceipt:
        command = command_fingerprint(request)
        if isinstance(request, ApplyZeroCandidateConfirmation):
            event_id = f"{request.idempotency_key.value}:zero-candidate-confirmed"
        else:
            event_id = f"{request.idempotency_key.value}:decision" if candidate_id is not None or isinstance(request, ApplyCustomerMatchingDecision) else None
        outbox = outbox_intent_ids
        if cross_domain_request is not None:
            outbox = (cross_domain_request.request_id,)
        if zero_candidate_decision is not None and zero_candidate_decision.decision is ZeroCandidateDecision.AGREE:
            outbox = (f"{zero_candidate_decision.event_id}:orders",)
        notifications: tuple[MatchingNotificationIntentProjection, ...] = ()
        if (
            isinstance(request, ApplyCustomerMatchingDecision)
            and result_state == "accepted"
            and candidate_id is not None
            and facts.package is not None
        ):
            candidate = next(
                item for item in facts.candidates if item.candidate_id == candidate_id
            )
            event_reference = event_id or f"{request.idempotency_key.value}:decision"
            notifications = (
                MatchingNotificationIntentProjection(
                    intent_id=f"{event_reference}:notify:customer",
                    recipient_role=MatchingNotificationRecipientRole.CUSTOMER,
                    recipient_subject_reference=f"case:{request.case_no}",
                    source_decision_event_id=event_reference,
                    criteria_snapshot_id=facts.package.criteria_snapshot_id,
                    package_id=facts.package.package_id,
                    package_version=facts.package.version,
                    package_fingerprint=facts.package.fingerprint,
                    candidate_id=candidate_id,
                    idempotency_key=request.idempotency_key,
                ),
                MatchingNotificationIntentProjection(
                    intent_id=f"{event_reference}:notify:caregiver",
                    recipient_role=MatchingNotificationRecipientRole.CAREGIVER,
                    recipient_subject_reference=f"staff:{candidate.staff_id}",
                    source_decision_event_id=event_reference,
                    criteria_snapshot_id=facts.package.criteria_snapshot_id,
                    package_id=facts.package.package_id,
                    package_version=facts.package.version,
                    package_fingerprint=facts.package.fingerprint,
                    candidate_id=candidate_id,
                    idempotency_key=request.idempotency_key,
                ),
            )
            outbox = tuple((*outbox, *(item.intent_id for item in notifications)))
        return MatchingApplyReceipt(
            f"{request.idempotency_key.value}:receipt",
            request.command_name,
            command,
            preview,
            facts.source_versions,
            event_id,
            resulting_package.package_id if resulting_package else (facts.package.package_id if facts.package else None),
            outbox,
            result_state,
            cross_domain_request,
            zero_candidate_decision,
            willingness_lineage,
            notifications,
            criteria_recontact_intents,
            resulting_package,
        )

    def _facts(self, request: QueryMatchingCoordination | str, facts: MatchingCoordinationFacts | None) -> MatchingCoordinationFacts:
        if facts is not None:
            return facts
        if self._read_port is None:
            raise ValueError("Phase A workflow requires typed facts or a read port")
        case_no = request.case_no if isinstance(request, QueryMatchingCoordination) else request
        return self._read_port.load(case_no)


def _zero_candidate_confirmation_package(
    request: PreviewZeroCandidateConfirmation | ApplyZeroCandidateConfirmation,
    facts: MatchingCoordinationFacts,
) -> MatchingPackage:
    parent = facts.package
    if (
        parent is None
        or parent.package_id != request.package_id
        or parent.version != request.package_version
        or parent.criteria_snapshot_id != request.criteria_snapshot_id
        or facts.snapshot.snapshot_id != request.criteria_snapshot_id
        or parent.state is not MatchingPackageState.CANDIDATE_POOL_OPEN
    ):
        raise _workflow_error(
            request.correlation_id,
            "matching_zero_candidate_confirmation_stale",
        )
    if any(
        candidate.eligibility.value == "eligible"
        and candidate.willingness == "willing"
        for candidate in facts.candidates
    ):
        raise _workflow_error(
            request.correlation_id,
            "matching_zero_candidate_confirmation_stale",
        )
    selection = fingerprint_payload(
        {
            "case_no": request.case_no,
            "criteria_snapshot_id": request.criteria_snapshot_id,
            "parent_package_id": parent.package_id,
            "parent_package_version": parent.version,
            "parent_package_fingerprint": parent.fingerprint.value,
            "source_versions": tuple(item.as_payload() for item in facts.source_versions),
            "reason": request.reason,
            "evidence": request.evidence,
        }
    )
    return MatchingPackage(
        package_id=f"matching:{request.case_no}:no-candidate:{selection.value[:24]}",
        version=parent.version + 1,
        mode=parent.mode,
        segments=(),
        required_service_dates=parent.required_service_dates,
        candidate_results=(),
        criteria_snapshot_id=parent.criteria_snapshot_id,
        source_versions=facts.source_versions,
        state=MatchingPackageState.NO_CANDIDATE,
        blockers=("no_legal_candidate",),
    )


def _validate_source_versions(expected: MatchingSourceTuple, current: MatchingSourceTuple, correlation_id: CorrelationId) -> None:
    if expected != current:
        raise _workflow_error(correlation_id, "matching_source_version_conflict")


def _validate_shift_dates(values: tuple[date, ...], field_name: str) -> None:
    if not isinstance(values, tuple) or not values or any(type(item) is not date for item in values):
        raise TypeError(f"{field_name} must be a non-empty date tuple")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be sorted and unique")


def _dates_overlap(values: tuple[date, ...], start: date, end: date | None) -> bool:
    return any(item >= start and (end is None or item <= end) for item in values)


def _require_willing_candidate(
    request: ApplyCustomerMatchingDecision,
    facts: MatchingCoordinationFacts,
    *,
    require_willing: bool,
) -> None:
    """Enforce the Eraser willing-pool branch before emitting a conversion reference."""

    if request.candidate_id is None:
        raise _workflow_error(
            request.correlation_id,
            "matching_customer_acceptance_not_conversion",
        )
    candidate = next(
        (item for item in facts.candidates if item.candidate_id == request.candidate_id),
        None,
    )
    if candidate is None:
        raise _workflow_error(request.correlation_id, "matching_candidate_not_found")
    if require_willing and (
        candidate.eligibility.value != "eligible" or candidate.willingness != "willing"
    ):
        raise _workflow_error(request.correlation_id, "matching_willingness_conflict")


def _workflow_error(correlation_id: CorrelationId, code: str) -> MatchingCoordinationWorkflowError:
    return MatchingCoordinationWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, code, code, correlation_id))


__all__ = [
    "MatchingCoordinationFacts",
    "MatchingCoordinationReadPort",
    "MatchingCoordinationWorkflow",
    "MatchingCoordinationWorkflowError",
    "ServiceDateShiftAvailabilityConfirmation",
    "ServiceDateShiftReassignmentReference",
]

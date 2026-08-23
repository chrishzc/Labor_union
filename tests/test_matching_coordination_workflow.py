"""
File: test_matching_coordination_workflow.py
Description: 驗證 M3 Phase A workflow 的唯讀、fresh source 與 accepted non-conversion 規則。
"""

from datetime import date, datetime, timezone

import pytest

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    MatchingCandidateResult,
    MatchingPackage,
    MatchingPackageMode,
    MatchingSegment,
    MatchingSourceVersion,
    SOURCE_KINDS,
    build_criteria_snapshot,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyCustomerMatchingDecision,
    ApplyZeroCandidateAlternative,
    PreviewCriteriaDiffResend,
    PreviewMatchingPackage,
    PreviewZeroCandidateAlternative,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationFacts,
    MatchingCoordinationWorkflow,
    MatchingCoordinationWorkflowError,
)


def _sources(seed: str = "c") -> tuple[MatchingSourceVersion, ...]:
    return tuple(MatchingSourceVersion(kind, f"{kind}:1", 1, seed * 64) for kind in SOURCE_KINDS)


def _facts(seed: str = "c") -> MatchingCoordinationFacts:
    sources = _sources(seed)
    snapshot = build_criteria_snapshot(
        snapshot_id="snapshot-1",
        case_no="CASE-001",
        criteria_version=1,
        criteria={"service_days": 2},
        source_versions=sources,
        created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    candidate = MatchingCandidateResult("candidate-1", 7, CandidateEligibility.ELIGIBLE, (), willingness="willing")
    package = MatchingPackage(
        package_id="package-1",
        version=1,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(7, (date(2026, 9, 1), date(2026, 9, 2)), 1),),
        required_service_dates=(date(2026, 9, 1), date(2026, 9, 2)),
        candidate_results=(candidate,),
        criteria_snapshot_id=snapshot.snapshot_id,
        source_versions=sources,
    )
    return MatchingCoordinationFacts(snapshot=snapshot, package=package, candidates=(candidate,), source_versions=sources)


def _common(seed: str = "c") -> dict[str, object]:
    return {
        "case_no": "CASE-001",
        "actor": ActorContext("admin_user_id:1"),
        "reason": "matching review",
        "correlation_id": CorrelationId("corr-matching-1"),
        "idempotency_key": IdempotencyKey("matching:case-001:workflow"),
        "expected_source_versions": _sources(seed),
    }


def test_query_and_preview_are_typed_and_do_not_mutate_facts() -> None:
    facts = _facts()
    workflow = MatchingCoordinationWorkflow()
    view = workflow.query("CASE-001", facts)
    diff = workflow.preview(
        PreviewCriteriaDiffResend(**_common(), before_snapshot_id="snapshot-1", after_snapshot_id="snapshot-1"),
        facts,
    )

    assert view is not None
    assert view.package_id == "package-1"
    assert diff.before_snapshot_id == "snapshot-1"
    assert facts.package is not None and facts.package.version == 1


def test_preview_package_uses_explicit_admin_selected_segments() -> None:
    original = _facts()
    required_dates = (date(2026, 9, 1), date(2026, 9, 3), date(2026, 9, 10))
    candidates = (
        MatchingCandidateResult(
            "candidate-2", 8, CandidateEligibility.ELIGIBLE, (),
            coverage_evidence=required_dates[2:], willingness="willing", staff_name="王小美",
        ),
        MatchingCandidateResult(
            "candidate-1", 7, CandidateEligibility.ELIGIBLE, (),
            coverage_evidence=required_dates[:2], willingness="willing", staff_name="林小明",
        ),
    )
    facts = MatchingCoordinationFacts(
        snapshot=original.snapshot,
        package=None,
        candidates=candidates,
        source_versions=original.source_versions,
    )
    command = PreviewMatchingPackage(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        required_service_dates=required_dates,
        segments=(
            MatchingSegment(7, required_dates[:2], 1),
            MatchingSegment(8, required_dates[2:], 2),
        ),
    )

    view = MatchingCoordinationWorkflow().preview(command, facts)

    assert view.mode is MatchingPackageMode.MULTI_SEGMENT
    assert tuple(item.staff_name for item in view.candidate_results) == ("林小明", "王小美")
    assert view.segments == ((7, required_dates[:2], 1), (8, required_dates[2:], 2))


def test_customer_accepted_creates_only_conversion_reference_and_not_assignment() -> None:
    facts = _facts()
    workflow = MatchingCoordinationWorkflow()
    command = ApplyCustomerMatchingDecision(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )

    decision = workflow.apply_customer_decision(command, facts)
    assert decision.accepted_is_not_contract_or_assignment is True
    assert decision.fresh_effects_status == "conversion_reference_requested"


def test_apply_fails_closed_when_source_tuple_is_stale() -> None:
    facts = _facts()
    command = ApplyCustomerMatchingDecision(
        **_common("d"),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )

    with pytest.raises(MatchingCoordinationWorkflowError) as captured:
        MatchingCoordinationWorkflow().apply(command, facts, preview_fingerprint=facts.package.fingerprint)
    assert captured.value.error.code == "matching_source_version_conflict"


def test_accepted_decision_returns_typed_conversion_request_and_stale_returns_rematch() -> None:
    facts = _facts()
    workflow = MatchingCoordinationWorkflow()
    command = ApplyCustomerMatchingDecision(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )
    receipt = workflow.apply(command, facts, preview_fingerprint=facts.package.fingerprint)
    assert receipt.cross_domain_request is not None
    assert receipt.cross_domain_request.request_kind.value == "assignment_conversion_requested"
    assert {item.recipient_role.value for item in receipt.notification_intents} == {
        "customer",
        "caregiver",
    }
    rematch = workflow.apply(command, facts, preview_fingerprint=facts.package.fingerprint, fresh_effects_match=False)
    assert rematch.cross_domain_request is not None
    assert rematch.cross_domain_request.request_kind.value == "rematch_requested"


def test_apply_customer_decision_rejects_stale_sources_and_unknown_candidate() -> None:
    facts = _facts()
    workflow = MatchingCoordinationWorkflow()
    stale = ApplyCustomerMatchingDecision(
        **_common("d"),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )
    with pytest.raises(MatchingCoordinationWorkflowError) as stale_error:
        workflow.apply_customer_decision(stale, facts)
    assert stale_error.value.error.code == "matching_source_version_conflict"

    unknown = ApplyCustomerMatchingDecision(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-missing",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )
    with pytest.raises(MatchingCoordinationWorkflowError) as candidate_error:
        workflow.apply_customer_decision(unknown, facts)
    assert candidate_error.value.error.code == "matching_candidate_not_found"


def test_customer_acceptance_requires_an_eligible_willing_candidate() -> None:
    facts = _facts()
    workflow = MatchingCoordinationWorkflow()
    missing_candidate = ApplyCustomerMatchingDecision(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id=None,
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )
    with pytest.raises(MatchingCoordinationWorkflowError) as missing_error:
        workflow.apply_customer_decision(missing_candidate, facts)
    assert missing_error.value.error.code == "matching_customer_acceptance_not_conversion"

    unwilling = MatchingCandidateResult(
        "candidate-1", 7, CandidateEligibility.ELIGIBLE, (), willingness="unwilling"
    )
    unwilling_facts = MatchingCoordinationFacts(
        snapshot=facts.snapshot,
        package=MatchingPackage(
            package_id="package-1",
            version=1,
            mode=MatchingPackageMode.SINGLE,
            segments=facts.package.segments,
            required_service_dates=facts.package.required_service_dates,
            candidate_results=(unwilling,),
            criteria_snapshot_id=facts.snapshot.snapshot_id,
            source_versions=facts.source_versions,
        ),
        candidates=(unwilling,),
        source_versions=facts.source_versions,
    )
    declined = ApplyCustomerMatchingDecision(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=unwilling_facts.package.fingerprint,
    )
    with pytest.raises(MatchingCoordinationWorkflowError) as unwilling_error:
        workflow.apply_customer_decision(declined, unwilling_facts)
    assert unwilling_error.value.error.code == "matching_willingness_conflict"

    rematch = workflow.apply_customer_decision(
        declined,
        unwilling_facts,
        fresh_effects_match=False,
    )
    assert rematch.fresh_effects_status == "rematch_required"
    assert rematch.rematch_reference == "matching:case-001:workflow:rematch"


def test_zero_candidate_disagreement_remains_awaiting_matching_without_outbox() -> None:
    candidate_facts = _facts()
    facts = MatchingCoordinationFacts(
        snapshot=candidate_facts.snapshot,
        package=None,
        candidates=(),
        source_versions=candidate_facts.source_versions,
    )
    workflow = MatchingCoordinationWorkflow()
    preview = workflow.preview(
        PreviewZeroCandidateAlternative(
            **_common(),
            criteria_snapshot_id="snapshot-1",
            policy_id="policy-v1",
            policy_version=1,
            relaxed_criteria=("service_days",),
        ),
        facts,
    )
    command = ApplyZeroCandidateAlternative(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        alternative_id=preview.alternative_id,
        policy_id="policy-v1",
        policy_version=1,
        relaxed_criteria=("service_days",),
        preview_fingerprint=preview.preview_fingerprint,
        decision="disagree",
    )
    receipt = workflow.apply(
        command,
        facts,
        preview_fingerprint=preview.preview_fingerprint,
    )
    assert receipt.result_state == "awaiting_matching"
    assert receipt.zero_candidate_decision is not None
    assert receipt.zero_candidate_decision.alternative_id == preview.alternative_id
    assert receipt.outbox_intent_ids == ()


def test_zero_candidate_agreement_queues_only_orders_before_owner_receipt() -> None:
    original = _facts()
    facts = MatchingCoordinationFacts(
        snapshot=original.snapshot,
        package=None,
        candidates=(),
        source_versions=original.source_versions,
    )
    workflow = MatchingCoordinationWorkflow()
    preview = workflow.preview(
        PreviewZeroCandidateAlternative(
            **_common(),
            criteria_snapshot_id="snapshot-1",
            policy_id="policy-v1",
            policy_version=1,
            relaxed_criteria=("service_days",),
        ),
        facts,
    )
    command = ApplyZeroCandidateAlternative(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        alternative_id=preview.alternative_id,
        policy_id="policy-v1",
        policy_version=1,
        relaxed_criteria=("service_days",),
        preview_fingerprint=preview.preview_fingerprint,
        decision="agree",
    )

    receipt = workflow.apply(
        command,
        facts,
        preview_fingerprint=preview.preview_fingerprint,
    )

    assert receipt.result_state == "alternative_agreed_pending_owning_workflows"
    assert receipt.outbox_intent_ids == (
        "matching:case-001:workflow:zero-candidate:orders",
    )


def test_zero_candidate_preview_uses_only_admin_selected_criteria() -> None:
    original = _facts()
    facts = MatchingCoordinationFacts(
        snapshot=original.snapshot,
        package=None,
        candidates=(),
        source_versions=original.source_versions,
    )
    command = PreviewZeroCandidateAlternative(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        policy_id="union-admin-manual-relaxation",
        policy_version=1,
        relaxed_criteria=("service_days",),
    )

    view = MatchingCoordinationWorkflow().preview(command, facts)

    assert view.relaxed_criteria == ("service_days",)
    assert view.unchanged_hard_criteria == ()
    assert view.candidate_result is None

    invalid = PreviewZeroCandidateAlternative(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        policy_id="union-admin-manual-relaxation",
        policy_version=1,
        relaxed_criteria=("unknown_criterion",),
    )
    with pytest.raises(MatchingCoordinationWorkflowError) as captured:
        MatchingCoordinationWorkflow().preview(invalid, facts)
    assert captured.value.error.code == "matching_alternative_not_explicit"

"""
File: test_matching_coordination_domain.py
Description: 驗證 Matching Coordination 的 source tuple、coverage 與 immutable domain 規則。
"""

import json
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    CriterionStatus,
    MatchingCandidateResult,
    MatchingCriteriaSnapshot,
    RefusalHistoryEntry,
    RefusalRouting,
    RefusalRoutingGroup,
    MatchingDecisionLineage,
    MatchingDomainError,
    MatchingPackage,
    MatchingPackageMode,
    MatchingSegment,
    MatchingSourceVersion,
    StableRejectionReason,
    SOURCE_KINDS,
    build_willingness_lineage,
    build_criteria_diff,
    build_manual_matching_package,
    build_criteria_snapshot,
    build_zero_candidate_alternative,
    canonical_source_tuple,
    route_refusal_history,
)


def _sources() -> tuple[MatchingSourceVersion, ...]:
    return tuple(
        MatchingSourceVersion(kind, f"{kind}:1", 1, "a" * 64)
        for kind in SOURCE_KINDS
    )


def _snapshot(snapshot_id: str, criteria: dict[str, object]) -> MatchingCriteriaSnapshot:
    return build_criteria_snapshot(
        snapshot_id=snapshot_id,
        case_no="CASE-001",
        criteria_version=1,
        criteria=criteria,
        source_versions=_sources(),
        created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )


def test_source_tuple_requires_all_frozen_sources_and_marks_unconsulted_explicitly() -> None:
    values = list(_sources())
    values[-1] = MatchingSourceVersion.not_consulted(SOURCE_KINDS[-1])
    result = canonical_source_tuple(values)

    assert tuple(item.source_kind for item in result) == SOURCE_KINDS
    assert result[-1].source_id == "not_consulted"
    with pytest.raises(MatchingDomainError):
        canonical_source_tuple(values[:-1])


def test_package_conserves_service_dates_and_rejects_overlap() -> None:
    candidate = MatchingCandidateResult(
        "candidate-1",
        7,
        CandidateEligibility.ELIGIBLE,
        (),
    )
    package = MatchingPackage(
        package_id="package-1",
        version=1,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(7, (date(2026, 9, 1), date(2026, 9, 2)), 1),),
        required_service_dates=(date(2026, 9, 1), date(2026, 9, 2)),
        candidate_results=(candidate,),
        criteria_snapshot_id="snapshot-1",
        source_versions=_sources(),
    )

    assert package.fingerprint is not None
    with pytest.raises(ValueError, match="fingerprint does not match"):
        replace(package, fingerprint="b" * 64)
    with pytest.raises(MatchingDomainError, match="conserve"):
        MatchingPackage(
            package_id="package-2",
            version=1,
            mode=MatchingPackageMode.SINGLE,
            segments=(MatchingSegment(7, (date(2026, 9, 1), date(2026, 9, 3)), 1),),
            required_service_dates=(date(2026, 9, 1), date(2026, 9, 2)),
            candidate_results=(candidate,),
            criteria_snapshot_id="snapshot-1",
            source_versions=_sources(),
        )


def test_manual_package_uses_admin_segments_and_sorts_candidates_by_name() -> None:
    required_dates = (
        date(2026, 9, 1),
        date(2026, 9, 3),
        date(2026, 9, 10),
    )
    candidates = (
        MatchingCandidateResult(
            "candidate-2",
            8,
            CandidateEligibility.ELIGIBLE,
            (),
            coverage_evidence=(date(2026, 9, 10),),
            willingness="willing",
            staff_name="王小美",
        ),
        MatchingCandidateResult(
            "candidate-1",
            7,
            CandidateEligibility.ELIGIBLE,
            (),
            coverage_evidence=(date(2026, 9, 1), date(2026, 9, 3)),
            willingness="willing",
            staff_name="林小明",
        ),
    )

    package = build_manual_matching_package(
        package_id="package-manual-1",
        version=1,
        segments=(
            MatchingSegment(7, required_dates[:2], 1),
            MatchingSegment(8, required_dates[2:], 2),
        ),
        required_service_dates=required_dates,
        candidate_results=candidates,
        criteria_snapshot_id="snapshot-1",
        source_versions=_sources(),
    )

    assert tuple(item.staff_name for item in package.candidate_results) == (
        "林小明",
        "王小美",
    )
    assert package.mode is MatchingPackageMode.MULTI_SEGMENT

    with pytest.raises(MatchingDomainError, match="does not cover"):
        build_manual_matching_package(
            package_id="package-manual-invalid",
            version=1,
            segments=(MatchingSegment(8, required_dates, 1),),
            required_service_dates=required_dates,
            candidate_results=candidates,
            criteria_snapshot_id="snapshot-1",
            source_versions=_sources(),
        )


def test_criteria_diff_and_accepted_lineage_keep_non_conversion_marker() -> None:
    before = _snapshot("snapshot-1", {"service_days": 10, "region": "east"})
    after = _snapshot("snapshot-2", {"service_days": 12, "region": "east", "hours": 8})
    diff = build_criteria_diff(before, after)
    assert diff.added == ("hours",)
    assert diff.changed == ("service_days",)
    assert diff.unchanged == ("region",)

    lineage = MatchingDecisionLineage(
        event_id="event-1",
        case_no="CASE-001",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        actor_id="admin_user_id:1",
        customer_state="accepted",
        caregiver_state="willing",
        fresh_effects_status="conversion_reference_requested",
        source_versions=_sources(),
    )
    assert lineage.accepted_is_not_contract_or_assignment is True


def test_zero_candidate_alternative_requires_explicit_policy_identity() -> None:
    alternative = build_zero_candidate_alternative(
        alternative_id="alternative-1",
        policy_id="policy-v1",
        policy_version=1,
        relaxed_criteria=("region",),
        unchanged_hard_criteria=("service_dates",),
        risk_warnings=("manual_confirmation_required",),
    )
    assert alternative.policy_id == "policy-v1"
    assert alternative.candidate_result is None


def test_criteria_diff_routes_refusal_history_into_exactly_one_group() -> None:
    before = _snapshot("snapshot-1", {"region": "east", "service_days": 10})
    after = _snapshot("snapshot-2", {"region": "west", "service_days": 10})
    routes = route_refusal_history(
        before,
        after,
        (
            RefusalHistoryEntry("refusal-1", "candidate-1", before.snapshot_id, "region_mismatch", ("region",), originally_willing=True),
            RefusalHistoryEntry("refusal-2", "candidate-2", before.snapshot_id, "region_mismatch", ("region",), pain_resolved=True),
            RefusalHistoryEntry("refusal-3", "candidate-3", before.snapshot_id, "buffer_conflict", ("buffer",)),
        ),
    )
    assert tuple(item.group for item in routes) == (
        RefusalRoutingGroup.GROUP1_ORIGINAL_WILLING_RECONFIRM,
        RefusalRoutingGroup.GROUP2_PAIN_RESOLVED_REPROBE,
        RefusalRoutingGroup.GROUP3_UNRELATED_SILENT_EXCLUDE,
    )


def test_criteria_diff_recipients_require_g1_or_g2_current_candidates() -> None:
    before = _snapshot("snapshot-recipient-before", {"region": "east"})
    after = _snapshot("snapshot-recipient-after", {"region": "west"})
    candidates = (
        MatchingCandidateResult(
            "candidate-g1", 1, CandidateEligibility.ELIGIBLE, (), willingness="willing"
        ),
        MatchingCandidateResult(
            "candidate-g2", 2, CandidateEligibility.ELIGIBLE, (), willingness="unwilling"
        ),
        MatchingCandidateResult(
            "candidate-g3", 3, CandidateEligibility.ELIGIBLE, (), willingness="willing"
        ),
        MatchingCandidateResult(
            "candidate-unrouted", 4, CandidateEligibility.ELIGIBLE, (), willingness="willing"
        ),
    )
    history = (
        RefusalHistoryEntry(
            "refusal-g1",
            "candidate-g1",
            before.snapshot_id,
            "region_mismatch",
            ("region",),
            originally_willing=True,
        ),
        RefusalHistoryEntry(
            "refusal-g2",
            "candidate-g2",
            before.snapshot_id,
            "region_mismatch",
            ("region",),
            pain_resolved=True,
        ),
        RefusalHistoryEntry(
            "refusal-g3",
            "candidate-g3",
            before.snapshot_id,
            "region_mismatch",
            ("region",),
        ),
        RefusalHistoryEntry(
            "refusal-unrouted",
            "candidate-unrouted",
            before.snapshot_id,
            "service_date_conflict",
            ("service_days",),
        ),
    )

    diff = build_criteria_diff(before, after, candidates, history)

    assert diff.affected_candidate_ids == tuple(sorted(diff.affected_candidate_ids))
    assert diff.affected_candidate_ids == (
        "candidate-g1",
        "candidate-g2",
        "candidate-g3",
        "candidate-unrouted",
    )
    assert diff.affected_candidate_ids
    assert diff.affected_recipient_ids == ("candidate-g1", "candidate-g2")
    assert diff.resend_eligible is True

    with pytest.raises(MatchingDomainError, match="lineage is incomplete"):
        build_criteria_diff(before, after, candidates[:1])


def test_willingness_lineage_derives_exact_g1_g2_g3_recipients() -> None:
    before = _snapshot("snapshot-impact-before", {"region": "east", "service_days": 2})
    after = _snapshot("snapshot-impact-after", {"region": "west", "service_days": 2})
    candidates = tuple(
        MatchingCandidateResult(
            f"candidate-g{index}",
            index,
            CandidateEligibility.ELIGIBLE,
            (),
            willingness="willing" if index == 1 else "unwilling",
        )
        for index in (1, 2, 3)
    )
    events = (
        build_willingness_lineage(event_id="event-g1", candidate_id="candidate-g1", staff_id=1, snapshot=before, previous_state="pending", current_state="willing", affected_criteria=("region", "service_days")),
        build_willingness_lineage(event_id="event-g2", candidate_id="candidate-g2", staff_id=2, snapshot=before, previous_state="pending", current_state="unwilling", reason_code="region_mismatch", affected_criteria=("region",)),
        build_willingness_lineage(event_id="event-g3", candidate_id="candidate-g3", staff_id=3, snapshot=before, previous_state="pending", current_state="unwilling", reason_code="service_date_conflict", affected_criteria=("service_days",)),
    )

    diff = build_criteria_diff(before, after, candidates, willingness_lineage=events)

    assert tuple(route.group.value for route in diff.refusal_routes) == (
        "group1_original_willing_reconfirm",
        "group2_pain_resolved_reprobe",
        "group3_unrelated_silent_exclude",
    )
    assert diff.affected_recipient_ids == ("candidate-g1", "candidate-g2")


def test_criteria_diff_rejects_ambiguous_candidate_impact_lineage() -> None:
    before = _snapshot("snapshot-ambiguous-before", {"region": "east"})
    after = _snapshot("snapshot-ambiguous-after", {"region": "west"})
    candidate = MatchingCandidateResult(
        "candidate-ambiguous",
        7,
        CandidateEligibility.ELIGIBLE,
        (),
        willingness="willing",
    )
    events = tuple(
        build_willingness_lineage(
            event_id=f"event-{index}",
            candidate_id=candidate.candidate_id,
            staff_id=candidate.staff_id,
            snapshot=before,
            previous_state="pending",
            current_state="willing",
            affected_criteria=("region",),
        )
        for index in (1, 2)
    )

    with pytest.raises(MatchingDomainError, match="lineage is ambiguous"):
        build_criteria_diff(before, after, (candidate,), willingness_lineage=events)

    explicit = RefusalHistoryEntry(
        "refusal-ambiguous",
        candidate.candidate_id,
        before.snapshot_id,
        "region_mismatch",
        ("region",),
        originally_willing=True,
    )
    with pytest.raises(MatchingDomainError, match="lineage is ambiguous"):
        build_criteria_diff(
            before,
            after,
            (candidate,),
            (explicit,),
            willingness_lineage=(events[0],),
        )


def test_stable_rejection_reasons_are_closed_and_keep_string_serialization() -> None:
    candidate = MatchingCandidateResult(
        "candidate-stable",
        7,
        CandidateEligibility.INELIGIBLE,
        (),
        rejection_reasons=(StableRejectionReason.BUFFER_CONFLICT, StableRejectionReason.REGION_MISMATCH),
    )
    assert candidate.rejection_reasons == ("buffer_conflict", "region_mismatch")
    assert json.dumps({"rejection_reasons": candidate.rejection_reasons}) == '{"rejection_reasons": ["buffer_conflict", "region_mismatch"]}'

    refusal = RefusalHistoryEntry(
        "refusal-stable",
        "candidate-stable",
        "snapshot-1",
        StableRejectionReason.REGION_MISMATCH,
    )
    route = RefusalRouting(
        "candidate-stable",
        refusal.refusal_id,
        RefusalRoutingGroup.GROUP3_UNRELATED_SILENT_EXCLUDE,
        "silent_exclude",
        StableRejectionReason.REGION_MISMATCH,
        refusal.snapshot_id,
        "a" * 64,
    )
    assert refusal.reason_code == "region_mismatch"
    assert route.reason_code == "region_mismatch"

    for invalid_reason in ("free_form", "no_candidate"):
        with pytest.raises(ValueError, match="stable rejection reason"):
            MatchingCandidateResult(
                "candidate-invalid",
                7,
                CandidateEligibility.INELIGIBLE,
                (),
                rejection_reasons=(invalid_reason,),
            )
        with pytest.raises(ValueError, match="stable rejection reason"):
            RefusalHistoryEntry("refusal-invalid", "candidate-invalid", "snapshot-1", invalid_reason)
        with pytest.raises(ValueError, match="stable rejection reason"):
            RefusalRouting(
                "candidate-invalid",
                "refusal-invalid",
                RefusalRoutingGroup.GROUP3_UNRELATED_SILENT_EXCLUDE,
                "silent_exclude",
                invalid_reason,
                "snapshot-1",
                "a" * 64,
            )


def test_changed_criteria_without_owner_pain_resolution_stays_silent() -> None:
    before = _snapshot("snapshot-silent-before", {"region": "east"})
    after = _snapshot("snapshot-silent-after", {"region": "west"})
    routes = route_refusal_history(
        before,
        after,
        (
            RefusalHistoryEntry(
                "refusal-silent",
                "candidate-silent",
                before.snapshot_id,
                "region_mismatch",
                ("region",),
            ),
        ),
    )

    assert routes[0].group is RefusalRoutingGroup.GROUP3_UNRELATED_SILENT_EXCLUDE


def test_refusal_history_unrelated_to_changed_criteria_is_silent_even_with_flags() -> None:
    before = _snapshot("snapshot-unrelated-before", {"region": "east", "service_days": 2})
    after = _snapshot("snapshot-unrelated-after", {"region": "west", "service_days": 2})
    routes = route_refusal_history(
        before,
        after,
        (
            RefusalHistoryEntry(
                "refusal-unrelated",
                "candidate-unrelated",
                before.snapshot_id,
                "buffer_conflict",
                ("buffer",),
                originally_willing=True,
            ),
        ),
    )

    assert routes[0].group is RefusalRoutingGroup.GROUP3_UNRELATED_SILENT_EXCLUDE
    assert routes[0].action == "silent_exclude"


def test_refusal_history_conflicting_routing_flags_fail_closed() -> None:
    before = _snapshot("snapshot-conflict-before", {"region": "east"})
    after = _snapshot("snapshot-conflict-after", {"region": "west"})

    with pytest.raises(MatchingDomainError, match="mutually exclusive"):
        route_refusal_history(
            before,
            after,
            (
                RefusalHistoryEntry(
                    "refusal-conflict",
                    "candidate-conflict",
                    before.snapshot_id,
                    "region_mismatch",
                    ("region",),
                    originally_willing=True,
                    pain_resolved=True,
                ),
            ),
        )


def test_snapshot_deep_immutability_and_willingness_lineage() -> None:
    snapshot = _snapshot("snapshot-1", {"nested": {"days": [1, 2]}})
    with pytest.raises(TypeError):
        snapshot.criteria["nested"]["days"] += (3,)  # type: ignore[index]
    lineage = build_willingness_lineage(
        event_id="willingness-1",
        candidate_id="candidate-1",
        staff_id=7,
        snapshot=snapshot,
        previous_state="pending",
        current_state="willing",
        affected_criteria=("nested",),
    )
    assert lineage.snapshot_id == snapshot.snapshot_id
    assert lineage.current_state == "willing"
    assert lineage.staff_id == 7
    assert lineage.affected_criteria == ("nested",)
    with pytest.raises(ValueError, match="transition is not supported"):
        build_willingness_lineage(
            event_id="willingness-invalid-transition",
            candidate_id="candidate-1",
            staff_id=7,
            snapshot=snapshot,
            previous_state="pending",
            current_state="silent_excluded",
            affected_criteria=("nested",),
        )

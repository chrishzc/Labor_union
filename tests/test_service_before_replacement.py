"""
File: test_service_before_replacement.py
Description: 驗證服務前換人候選的分流、沿革、重用證明與安全停止。
"""

from datetime import date

import pytest

from domains.scheduling.service_before_replacement import (
    ActualServiceProof,
    CandidatePoolReuseProof,
    MatchingZeroCandidateProof,
    ReplacementOutcome,
    ReplacementResumeStep,
    ReplacementRootIdentity,
    ReplacementRootKind,
    ReplacementScenario,
    ServiceBeforeReplacementError,
    ServiceBeforeReplacementFacts,
    SuccessorRoundFact,
    preview_service_before_replacement,
    query_service_before_replacement,
)
from shared_kernel.fingerprints import fingerprint_payload


CASE = "CASE-RPRE-1"


def _root(kind: ReplacementRootKind, root_id: str, *, current: bool = True):
    return ReplacementRootIdentity(kind, root_id, CASE, current=current)


def _facts(
    scenario=ReplacementScenario.R02,
    *,
    service_dates=(),
    roots=None,
    proof=None,
    zero_candidate_proof=None,
):
    if roots is None:
        roots = tuple(
            _root(kind, f"{kind.value}:old")
            for kind in {
                ReplacementScenario.R01: (ReplacementRootKind.CANDIDATE_BINDING, ReplacementRootKind.WILLINGNESS),
                ReplacementScenario.R02: (ReplacementRootKind.MATCHING_PLAN, ReplacementRootKind.MATCHING_SEGMENT, ReplacementRootKind.MATCHING_REPLY, ReplacementRootKind.RECIPIENT_CONFIRMATION),
                ReplacementScenario.R03: (ReplacementRootKind.WAITING_LOCK, ReplacementRootKind.COMMITMENT, ReplacementRootKind.SIGNBACK, ReplacementRootKind.RECIPIENT_BINDING),
                ReplacementScenario.R04: (ReplacementRootKind.EFFECTIVE_GENERATION, ReplacementRootKind.ASSIGNMENT, ReplacementRootKind.OFFICIAL_SCHEDULE),
                ReplacementScenario.R07: (),
            }[scenario]
        )
    service_proof = ActualServiceProof(
        CASE,
        tuple(service_dates),
        "official-service:event:old",
        13,
    )
    successor_round = None
    if scenario is ReplacementScenario.R07 and zero_candidate_proof is None:
        successor_round = SuccessorRoundFact(
            CASE,
            "successor-round:existing",
            "replacement-generation:existing",
            "replacement-event:existing",
            9,
            14,
            0,
            "zero_candidate_successor_disposition",
        )
    return ServiceBeforeReplacementFacts(
        CASE,
        scenario,
        tuple(service_dates),
        "generation:old",
        "event:old",
        8,
        13,
        roots,
        (_root(ReplacementRootKind.CANDIDATE_BINDING, "candidate:history", current=False),),
        proof,
        True,
        service_proof,
        8,
        "aggregate:old",
        CASE,
        "caregiver_requested_replacement",
        ("case-note:1",),
        successor_round,
        "round:1",
        "candidate:1",
        zero_candidate_proof,
    )


def _proof(*, accepted=False, same_round=True, coverage=True, availability=True, willingness=True, fresh=True):
    return CandidatePoolReuseProof(
        "pool:1",
        "round:1",
        2,
        3,
        4,
        fingerprint_payload({"pool": 1}),
        same_round,
        coverage,
        availability,
        willingness,
        fresh,
        accepted,
        CASE,
        "round:1",
        8,
        13,
        "candidate:1",
    )


def _zero_candidate_proof() -> MatchingZeroCandidateProof:
    return MatchingZeroCandidateProof(
        CASE,
        "matching:CASE-RPRE-1:no-candidate:proof",
        3,
        "snapshot-1",
        "matching:CASE-RPRE-1:zero-candidate-confirmed",
        3,
        fingerprint_payload({"matching-package": "no-candidate"}),
        fingerprint_payload({"matching-event": "zero-candidate-confirmed"}),
        "matching:zero:confirm:receipt",
        "matching:zero:confirm:zero-candidate-confirmed:assignment",
    )


@pytest.mark.parametrize("scenario", tuple(ReplacementScenario))
def test_zero_service_creates_strictly_new_successor_and_exact_branch_roots(scenario):
    candidate = preview_service_before_replacement(_facts(scenario))

    if scenario is ReplacementScenario.R07:
        assert candidate.outcome is ReplacementOutcome.BLOCKED
        assert candidate.created_root_ids == ()
        assert candidate.successor_round_identity == "successor-round:existing"
        return

    assert candidate.prior_generation_identity == "generation:old"
    assert candidate.resulting_generation_version == 9
    assert candidate.resulting_event_version == 14
    assert candidate.replacement_generation_identity != candidate.prior_generation_identity
    assert candidate.replacement_event_identity != candidate.prior_event_identity
    assert candidate.created_root_ids == ("successor-round:CASE-RPRE-1:14",)
    assert not set(candidate.retained_root_ids) & set(candidate.superseded_root_ids)
    assert all(not root.current for root in candidate.retained_roots if root.root_id == "candidate:history")


@pytest.mark.parametrize("scenario", tuple(ReplacementScenario)[:-1])
def test_each_r_branch_supersedes_only_its_exact_current_caregiver_roots(scenario):
    candidate = preview_service_before_replacement(_facts(scenario))
    expected = {
        ReplacementScenario.R01: {"candidate_binding:old", "willingness:old"},
        ReplacementScenario.R02: {"matching_plan:old", "matching_segment:old", "matching_reply:old", "recipient_confirmation:old"},
        ReplacementScenario.R03: {"waiting_lock:old", "commitment:old", "signback:old", "recipient_binding:old"},
        ReplacementScenario.R04: {"effective_generation:old", "assignment:old", "official_schedule:old"},
    }[scenario]
    assert set(candidate.superseded_root_ids) == expected
    assert candidate.superseded_root_ids == tuple(sorted(candidate.superseded_root_ids))
    assert "candidate:history" in candidate.retained_root_ids


def test_server_owns_step_two_three_four_and_reuse_proof_is_required():
    assert query_service_before_replacement(_facts()).resume_step is ReplacementResumeStep.STEP_2
    assert query_service_before_replacement(_facts(proof=_proof())).resume_step is ReplacementResumeStep.STEP_3
    assert query_service_before_replacement(_facts(proof=_proof(accepted=True))).resume_step is ReplacementResumeStep.STEP_4
    assert query_service_before_replacement(_facts(proof=_proof(accepted=True, coverage=False))).resume_step is ReplacementResumeStep.STEP_2


def test_preview_rebinds_fresh_reuse_proof_to_new_successor_round():
    candidate = preview_service_before_replacement(_facts(proof=_proof(accepted=True)))

    assert candidate.resume_step is ReplacementResumeStep.STEP_4
    assert candidate.candidate_pool_reuse_proof is not None
    assert candidate.candidate_pool_reuse_proof.round_identity == candidate.successor_round_identity
    assert candidate.candidate_pool_reuse_proof.successor_round_identity == candidate.successor_round_identity
    assert candidate.candidate_pool_reuse_proof.generation_version == candidate.expected_generation_version
    assert candidate.candidate_pool_reuse_proof.event_version == candidate.expected_event_version


def test_r07_zero_candidate_is_concrete_blocked_disposition_without_reviving_old_staff():
    old_staff = _root(ReplacementRootKind.CANDIDATE_BINDING, "staff:old")
    facts = _facts(ReplacementScenario.R07, roots=(old_staff,))
    query = query_service_before_replacement(facts)
    candidate = preview_service_before_replacement(facts)

    assert query.blockers == ("zero_candidate_successor_disposition",)
    assert query.resume_step is ReplacementResumeStep.STEP_2
    assert query.root_delta is None
    assert candidate.outcome is ReplacementOutcome.BLOCKED
    assert candidate.blockers == ("zero_candidate_successor_disposition",)
    assert candidate.resume_step is ReplacementResumeStep.STEP_2
    assert candidate.superseded_root_ids == ()
    assert candidate.created_root_ids == ()
    assert candidate.successor_round_identity == "successor-round:existing"
    assert "staff:old" in candidate.retained_root_ids


def test_r07_post_apply_query_retains_successor_without_marking_it_impacted():
    successor_root = _root(
        ReplacementRootKind.SUCCESSOR_ROUND,
        "successor-round:existing",
    )
    facts = _facts(ReplacementScenario.R07, roots=(successor_root,))

    query = query_service_before_replacement(facts)

    assert query.blockers == ("zero_candidate_successor_disposition",)
    assert query.impacted_root_ids == ()
    assert "successor-round:existing" in query.retained_root_ids


def test_r07_matching_owner_proof_is_ready_once_then_becomes_step_two_successor() -> None:
    proof = _zero_candidate_proof()
    facts = _facts(ReplacementScenario.R07, zero_candidate_proof=proof)

    query = query_service_before_replacement(facts)
    candidate = preview_service_before_replacement(facts)

    assert query.blockers == ()
    assert query.resume_step is ReplacementResumeStep.STEP_2
    assert candidate.outcome is ReplacementOutcome.READY
    assert candidate.can_apply is True
    assert candidate.resume_step is ReplacementResumeStep.STEP_2
    assert candidate.matching_zero_candidate_proof == proof
    assert candidate.created_root_ids == (
        "successor-round:CASE-RPRE-1:14",
    )
    assert candidate.superseded_root_ids == ()


def test_any_actual_service_is_substitution_referral_and_zero_write():
    candidate = preview_service_before_replacement(
        _facts(service_dates=(date(2026, 8, 28),))
    )

    assert candidate.outcome is ReplacementOutcome.SUBSTITUTION_REFERRAL
    assert candidate.zero_write is True
    assert candidate.replacement_event_identity is None
    assert candidate.created_root_ids == ()
    assert candidate.blockers == ("actual_service_exists",)


def test_missing_exact_root_set_is_blocked_without_a_partial_candidate():
    facts = _facts(ReplacementScenario.R04, roots=(_root(ReplacementRootKind.ASSIGNMENT, "assignment:old"),))
    candidate = preview_service_before_replacement(facts)
    assert candidate.outcome is ReplacementOutcome.BLOCKED
    assert candidate.blockers == ("replacement_root_set_incomplete",)
    assert candidate.zero_write is True


def test_root_case_mismatch_is_rejected_before_preview():
    with pytest.raises(ServiceBeforeReplacementError, match="replacement_root_case_mismatch"):
        ServiceBeforeReplacementFacts(
            CASE,
            ReplacementScenario.R01,
            (),
            "generation:old",
            "event:old",
            1,
            1,
            (ReplacementRootIdentity(ReplacementRootKind.WILLINGNESS, "w:1", "OTHER"),),
        )


def test_required_root_kind_is_exactly_one_and_duplicate_kind_is_zero_write():
    roots = tuple(_root(kind, f"{kind.value}:old") for kind in (
        ReplacementRootKind.EFFECTIVE_GENERATION,
        ReplacementRootKind.ASSIGNMENT,
        ReplacementRootKind.OFFICIAL_SCHEDULE,
        ReplacementRootKind.ASSIGNMENT,
    ))
    with pytest.raises(ServiceBeforeReplacementError, match="replacement_root_identity_not_unique"):
        _facts(ReplacementScenario.R04, roots=roots)


def test_current_and_retained_root_identity_cannot_cross_sets():
    with pytest.raises(ServiceBeforeReplacementError, match="replacement_root_cross_set_identity"):
        ServiceBeforeReplacementFacts(
            CASE, ReplacementScenario.R02, (), "generation:old", "event:old", 8, 13,
            _facts().current_roots, (_root(ReplacementRootKind.MATCHING_PLAN, "matching_plan:old", current=False),),
            actual_service_proof=ActualServiceProof(CASE, (), "official-service:event:old", 13),
            actual_service_proof_available=True,
        )


def test_authoritative_service_proof_is_case_bound_and_fingerprint_checked():
    with pytest.raises(ServiceBeforeReplacementError, match="actual_service_proof_fingerprint_mismatch"):
        ActualServiceProof(CASE, (), "official-service:event:old", 13, fingerprint_payload({"wrong": 1}))
    with pytest.raises(ServiceBeforeReplacementError, match="actual_service_proof_case_or_dates_mismatch"):
        ServiceBeforeReplacementFacts(
            CASE, ReplacementScenario.R01, (), "generation:old", "event:old", 8, 13,
            tuple(_root(kind, f"{kind.value}:old") for kind in (ReplacementRootKind.CANDIDATE_BINDING, ReplacementRootKind.WILLINGNESS)),
            actual_service_proof=ActualServiceProof("OTHER", (), "official-service:event:old", 13),
        )


def test_unbound_candidate_pool_reuse_stops_at_step_two():
    candidate = preview_service_before_replacement(_facts(proof=_proof()).__class__(
        CASE, ReplacementScenario.R02, (), "generation:old", "event:old", 8, 13,
        _facts().current_roots, _facts().retained_history,
        CandidatePoolReuseProof("pool:1", "round:other", 2, 3, 4, fingerprint_payload({"pool": 1}), True, True, True, True, True, False, CASE, "round:other", 8, 13, "candidate:1"),
        True, ActualServiceProof(CASE, (), "official-service:event:old", 13), 8, "aggregate:old", CASE,
        "caregiver_requested_replacement", ("case-note:1",), None, "round:1",
    ))
    assert candidate.zero_write is True
    assert candidate.blockers == ("candidate_pool_reuse_unbound",)
    assert query_service_before_replacement(_facts(proof=CandidatePoolReuseProof(
        "pool:1", "round:other", 2, 3, 4, fingerprint_payload({"pool": 1}),
        True, True, True, True, True, False, CASE, "round:other", 8, 13, "candidate:1",
    ))).resume_step is ReplacementResumeStep.STEP_2


def test_r07_without_existing_successor_round_never_invents_one():
    facts = _facts(ReplacementScenario.R07)
    facts = ServiceBeforeReplacementFacts(
        facts.case_no, facts.scenario, facts.actual_service_dates, facts.prior_generation_identity,
        facts.prior_event_identity, facts.generation_version, facts.event_version, facts.current_roots,
        facts.retained_history, facts.candidate_pool_reuse, facts.actual_service_proof_available,
        facts.actual_service_proof, facts.aggregate_version, facts.prior_aggregate_identity,
        facts.prior_case_no, facts.replacement_reason, facts.reason_evidence, None,
    )
    candidate = preview_service_before_replacement(facts)
    assert candidate.blockers == ("successor_round_missing",)
    assert candidate.created_root_ids == ()
    assert candidate.replacement_event_identity is None


def test_r04_marks_matching_only_zero_service_without_relaxing_assignment_plan():
    candidate = preview_service_before_replacement(_facts(ReplacementScenario.R04))
    assert candidate.projection_kind.value == "matching_only_zero_service"
    assert candidate.actual_service_dates == ()


def test_complete_candidate_fingerprint_covers_reason_and_authoritative_proof():
    first = preview_service_before_replacement(_facts())
    second = preview_service_before_replacement(
        ServiceBeforeReplacementFacts(
            CASE, ReplacementScenario.R02, (), "generation:old", "event:old", 8, 13,
            _facts().current_roots, _facts().retained_history, None, True,
            ActualServiceProof(CASE, (), "official-service:other", 14), 8, "aggregate:old", CASE,
            "different-reason", ("case-note:2",), None, "round:1",
        )
    )
    assert first.fingerprint != second.fingerprint

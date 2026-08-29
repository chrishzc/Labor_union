"""
File: test_service_before_replacement_projection.py
Description: 驗證服務前換人異常的純投影與 fail-closed 狀態。
"""

import random
from dataclasses import replace
from datetime import date
from hashlib import sha256

import pytest

from domains.scheduling.service_before_replacement import (
    AuthoritativeActualServiceProof,
    CandidatePoolReuseProof,
    ReplacementScenario,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.service_before_replacement_projection import (
    CurrentStepOwnerReadback,
    ReplacementLineageReadback,
    ReplacementOutboxReadback,
    ReplacementReceiptReadback,
    ReplacementRootReadback,
    ReplacementSuccessorReadback,
    ServiceBeforeReplacementProjectionInput,
    ServiceBeforeReplacementProjectionStatus,
    project_service_before_replacement_occurrence,
)


def _input(*, scenario=ReplacementScenario.R01, current_step=2, service_dates=()):
    case_no = "CASE-RPRE-001"
    event_identity = "replacement-event:CASE-RPRE-001:9"
    round_identity = "successor-round:CASE-RPRE-001:9"
    lineage = ReplacementLineageReadback(
        case_no=case_no,
        scenario=scenario,
        prior_generation_identity="generation:CASE-RPRE-001:8",
        replacement_generation_identity="replacement-generation:CASE-RPRE-001:9",
        prior_event_identity="event:CASE-RPRE-001:8",
        replacement_event_identity=event_identity,
        expected_aggregate_version=8,
        resulting_aggregate_version=9,
        expected_generation_version=8,
        resulting_generation_version=9,
        expected_event_version=8,
        resulting_event_version=9,
    )
    root_specs = {
        ReplacementScenario.R01: (
            ("candidate-binding:CASE-RPRE-001:old", "matching", "candidate_binding"),
            ("willingness:CASE-RPRE-001:old", "matching", "willingness"),
        ),
        ReplacementScenario.R02: (
            ("matching-plan:CASE-RPRE-001:old", "matching", "matching_plan"),
            ("matching-segment:CASE-RPRE-001:old", "matching", "matching_segment"),
            ("matching-reply:CASE-RPRE-001:old", "matching", "matching_reply"),
            ("recipient-confirmation:CASE-RPRE-001:old", "matching", "recipient_confirmation"),
        ),
        ReplacementScenario.R03: (
            ("waiting-lock:CASE-RPRE-001:old", "scheduling", "waiting_lock"),
            ("commitment:CASE-RPRE-001:old", "scheduling", "commitment"),
            ("signback:CASE-RPRE-001:old", "scheduling", "signback"),
            ("recipient-binding:CASE-RPRE-001:old", "scheduling", "recipient_binding"),
        ),
        ReplacementScenario.R04: (
            ("effective-generation:CASE-RPRE-001:old", "scheduling", "effective_generation"),
            ("assignment:CASE-RPRE-001:old", "scheduling", "assignment"),
            ("official-schedule:CASE-RPRE-001:old", "scheduling", "official_schedule"),
        ),
        ReplacementScenario.R07: (),
    }[scenario]
    roots = tuple(
        ReplacementRootReadback(identity, owner, kind, "superseded", False, case_no)
        for identity, owner, kind in root_specs
    ) + (
        ReplacementRootReadback(
            "unrelated-root:CASE-RPRE-001:old", "matching", "candidate_binding", "retained", False, case_no
        ),
        ReplacementRootReadback(
            round_identity, "matching", "successor_round", "created", True, case_no
        ),
    )
    successor = ReplacementSuccessorReadback(
        case_no=case_no,
        replacement_event_identity=event_identity,
        successor_round_identity=round_identity,
        candidate_count=1,
        resume_step="step_2",
        matching_package_lineage_id=101,
        matching_event_id=202,
    )
    retained_ids = ("unrelated-root:CASE-RPRE-001:old",)
    superseded_ids = tuple(identity for identity, _, _ in root_specs)
    created_ids = (round_identity,)
    receipt = ReplacementReceiptReadback(
        case_no=case_no,
        receipt_identity="replacement-receipt:CASE-RPRE-001:9",
        replacement_event_identity=event_identity,
        successor_round_identity=round_identity,
        resulting_aggregate_version=9,
        resulting_generation_version=9,
        resulting_event_version=9,
        outbox_identity="replacement-outbox:CASE-RPRE-001:9",
        retained_root_ids=retained_ids,
        superseded_root_ids=superseded_ids,
        created_root_ids=created_ids,
        retained_root_set_digest=_digest(retained_ids),
        superseded_root_set_digest=_digest(superseded_ids),
        created_root_set_digest=_digest(created_ids),
        retained_root_count=len(retained_ids),
        superseded_root_count=len(superseded_ids),
        created_root_count=len(created_ids),
    )
    outbox = ReplacementOutboxReadback(
        case_no=case_no,
        replacement_event_identity=event_identity,
        receipt_identity=receipt.receipt_identity,
        outbox_identity=receipt.outbox_identity,
    )
    proof = AuthoritativeActualServiceProof(
        case_no=case_no,
        service_dates=tuple(service_dates),
        source_identity="scheduling-official-service:CASE-RPRE-001",
        source_version=3,
    )
    step = CurrentStepOwnerReadback(case_no=case_no, current_step=current_step)
    return ServiceBeforeReplacementProjectionInput(
        lineage=lineage,
        roots=roots,
        successor=successor,
        receipt=receipt,
        outbox=outbox,
        actual_service_proof=proof,
        current_step=step,
    )


def _digest(values):
    return sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()


def test_terminal_projection_is_deterministic_for_complete_zero_service_readback():
    source = _input()

    first = project_service_before_replacement_occurrence(source)
    second = project_service_before_replacement_occurrence(source)

    assert first.status is ServiceBeforeReplacementProjectionStatus.TERMINAL
    assert first == second
    assert len(first.occurrence_identity) <= 191
    assert first.occurrence_identity.startswith("service-before-replacement:")
    assert first.current_step == 2
    assert first.blockers == ()


@pytest.mark.parametrize("scenario", tuple(ReplacementScenario))
def test_projection_fingerprint_is_stable_for_readback_permutations(scenario):
    source = _input(scenario=scenario)
    if scenario is ReplacementScenario.R07:
        source = replace(
            source,
            successor=replace(
                source.successor,
                candidate_count=0,
                zero_candidate_disposition="blocked_no_candidate",
            ),
        )

    expected = project_service_before_replacement_occurrence(source)
    for seed in range(8):
        randomizer = random.Random(seed)
        receipt = source.receipt
        shuffled_receipt = replace(
            receipt,
            retained_root_ids=tuple(randomizer.sample(receipt.retained_root_ids, len(receipt.retained_root_ids))),
            superseded_root_ids=tuple(
                randomizer.sample(receipt.superseded_root_ids, len(receipt.superseded_root_ids))
            ),
            created_root_ids=tuple(randomizer.sample(receipt.created_root_ids, len(receipt.created_root_ids))),
        )
        shuffled = replace(
            source,
            roots=tuple(randomizer.sample(source.roots, len(source.roots))),
            receipt=shuffled_receipt,
        )

        actual = project_service_before_replacement_occurrence(shuffled)

        assert actual == expected


@pytest.mark.parametrize("scenario", [ReplacementScenario.R02, ReplacementScenario.R03, ReplacementScenario.R04])
def test_r01_to_r04_complete_readback_is_terminal(scenario):
    projection = project_service_before_replacement_occurrence(_input(scenario=scenario))

    assert projection.status is ServiceBeforeReplacementProjectionStatus.TERMINAL


def test_r07_zero_candidate_successor_is_blocked_not_terminal():
    source = _input(scenario=ReplacementScenario.R07)
    source = source.__class__(
        lineage=source.lineage,
        roots=source.roots,
        successor=ReplacementSuccessorReadback(
                case_no=source.lineage.case_no,
                replacement_event_identity=source.lineage.replacement_event_identity,
                successor_round_identity=source.successor.successor_round_identity,
                candidate_count=0,
                zero_candidate_disposition="blocked_no_candidate",
                resume_step="step_2",
                matching_package_lineage_id=101,
                matching_event_id=202,
            ),
        receipt=source.receipt,
        outbox=source.outbox,
        actual_service_proof=source.actual_service_proof,
        current_step=CurrentStepOwnerReadback(
                case_no=source.lineage.case_no, current_step=2
            ),
    )

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.BLOCKED
    assert projection.blockers == ("zero_candidate_successor",)


def test_actual_service_positive_keeps_occurrence_active_for_substitution_referral():
    projection = project_service_before_replacement_occurrence(
        _input(service_dates=(date(2026, 8, 28),))
    )

    assert projection.status is ServiceBeforeReplacementProjectionStatus.ACTIVE
    assert projection.outcome == "substitution_referral"
    assert projection.blockers == ("actual_service_exists",)
    assert projection.terminal is False


def test_actual_service_referral_short_circuits_missing_replacement_artifacts():
    source = _input(service_dates=(date(2026, 8, 28),))
    source = replace(source, roots=None, successor=None, receipt=None, outbox=None, current_step=None)

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.ACTIVE
    assert projection.blockers == ("actual_service_exists",)
    assert projection.error_code is None
    assert projection.replacement_event_identity is None
    assert projection.successor_round_identity is None
    assert projection.retained_root_ids == ()
    assert projection.superseded_root_ids == ()
    assert projection.created_root_ids == ()


def test_normal_empty_successor_pool_remains_active():
    source = _input()
    successor = ReplacementSuccessorReadback(
        case_no=source.lineage.case_no,
        replacement_event_identity=source.lineage.replacement_event_identity,
        successor_round_identity=source.successor.successor_round_identity,
        candidate_count=0,
        resume_step="step_2",
        matching_package_lineage_id=101,
        matching_event_id=202,
    )
    source = source.__class__(
        lineage=source.lineage,
        roots=source.roots,
        successor=successor,
        receipt=source.receipt,
        outbox=source.outbox,
        actual_service_proof=source.actual_service_proof,
        current_step=source.current_step,
    )

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.ACTIVE
    assert projection.blockers == ("successor_candidate_pool_empty",)


def test_missing_successor_readback_remains_active_and_fail_closed():
    source = _input()
    source = source.__class__(
        lineage=source.lineage,
        roots=source.roots,
        successor=None,
        receipt=source.receipt,
        outbox=source.outbox,
        actual_service_proof=source.actual_service_proof,
        current_step=source.current_step,
    )

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.error_code == "replacement_successor_readback_unavailable"
    assert projection.terminal is False


def test_missing_current_step_is_typed_unavailable_and_never_terminal():
    source = _input()
    source = source.__class__(
        lineage=source.lineage,
        roots=source.roots,
        successor=source.successor,
        receipt=source.receipt,
        outbox=source.outbox,
        actual_service_proof=source.actual_service_proof,
        current_step=None,
    )

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.availability == "unavailable"
    assert projection.error_code == "current_step_readback_unavailable"
    assert projection.terminal is False


def test_receipt_set_drift_is_outcome_unknown():
    source = _input()
    receipt = ReplacementReceiptReadback(
        case_no=source.receipt.case_no,
        receipt_identity=source.receipt.receipt_identity,
        replacement_event_identity=source.receipt.replacement_event_identity,
        successor_round_identity=source.receipt.successor_round_identity,
        resulting_aggregate_version=source.receipt.resulting_aggregate_version,
        resulting_generation_version=source.receipt.resulting_generation_version,
        resulting_event_version=source.receipt.resulting_event_version,
        outbox_identity=source.receipt.outbox_identity,
        retained_root_ids=("assignment:drift", "waiting-lock:old"),
        superseded_root_ids=source.receipt.superseded_root_ids,
        created_root_ids=source.receipt.created_root_ids,
        retained_root_set_digest=_digest(("assignment:drift", "waiting-lock:old")),
        superseded_root_set_digest=_digest(source.receipt.superseded_root_ids),
        created_root_set_digest=source.receipt.created_root_set_digest,
        retained_root_count=2,
        superseded_root_count=source.receipt.superseded_root_count,
        created_root_count=source.receipt.created_root_count,
    )
    source = source.__class__(
        lineage=source.lineage,
        roots=source.roots,
        successor=source.successor,
        receipt=receipt,
        outbox=source.outbox,
        actual_service_proof=source.actual_service_proof,
        current_step=source.current_step,
    )

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.error_code == "replacement_root_set_mismatch"


@pytest.mark.parametrize(
    "field, value",
    [
        ("case_no", "OTHER-CASE"),
        ("outbox_identity", "different-outbox"),
    ],
)
def test_cross_case_or_outbox_mismatch_fails_closed(field, value):
    source = _input()
    if field == "case_no":
        roots = tuple(
            ReplacementRootReadback(
                root.root_identity,
                root.owner_domain,
                root.root_kind,
                root.disposition,
                root.current,
                value,
            )
            for root in source.roots
        )
        source = source.__class__(
            lineage=source.lineage,
            roots=roots,
            successor=source.successor,
            receipt=source.receipt,
            outbox=source.outbox,
            actual_service_proof=source.actual_service_proof,
            current_step=source.current_step,
        )
    else:
        source = source.__class__(
            lineage=source.lineage,
            roots=source.roots,
            successor=source.successor,
            receipt=source.receipt,
            outbox=ReplacementOutboxReadback(
                case_no=source.outbox.case_no,
                replacement_event_identity=source.outbox.replacement_event_identity,
                receipt_identity=source.outbox.receipt_identity,
                outbox_identity=value,
            ),
            actual_service_proof=source.actual_service_proof,
            current_step=source.current_step,
        )

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.terminal is False


@pytest.mark.parametrize(
    "field",
    [
        "prior_generation_identity",
        "replacement_generation_identity",
        "prior_event_identity",
        "replacement_event_identity",
        "successor_round_identity",
        "receipt_identity",
        "outbox_identity",
    ],
)
def test_every_replacement_identity_is_case_bound(field):
    source = _input()
    lineage = source.lineage
    if field in {
        "prior_generation_identity",
        "replacement_generation_identity",
        "prior_event_identity",
        "replacement_event_identity",
    }:
        lineage = replace(lineage, **{field: f"{field}:OTHER-CASE:9"})
        source = replace(source, lineage=lineage)
    elif field == "successor_round_identity":
        successor = replace(source.successor, successor_round_identity="successor-round:OTHER-CASE:9")
        source = replace(source, successor=successor)
    elif field == "receipt_identity":
        receipt = replace(source.receipt, receipt_identity="replacement-receipt:OTHER-CASE:9")
        outbox = replace(source.outbox, receipt_identity=receipt.receipt_identity)
        source = replace(source, receipt=receipt, outbox=outbox)
    else:
        outbox = replace(source.outbox, outbox_identity="replacement-outbox:OTHER-CASE:9")
        source = replace(source, outbox=outbox)

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.error_code == "replacement_identity_case_mismatch"


def test_occurrence_identity_is_canonical_and_length_safe():
    source = _input()
    long_event = "replacement-event:CASE-RPRE-001:" + ("x" * 150)
    source = replace(source, lineage=replace(source.lineage, replacement_event_identity=long_event))

    projection = project_service_before_replacement_occurrence(source)

    assert len(projection.occurrence_identity) <= 191
    assert projection.occurrence_identity.startswith("service-before-replacement:")
    assert projection.occurrence_identity != (
        "service-before-replacement:CASE-RPRE-001:R-01:" + long_event
    )


def test_projection_fingerprint_covers_receipt_and_outbox_readback():
    source = _input()
    changed_receipt = replace(
        source.receipt,
        receipt_identity="replacement-receipt:CASE-RPRE-001:10",
        outbox_identity="replacement-outbox:CASE-RPRE-001:10",
    )
    changed_outbox = replace(
        source.outbox,
        receipt_identity=changed_receipt.receipt_identity,
        outbox_identity=changed_receipt.outbox_identity,
    )
    changed = replace(source, receipt=changed_receipt, outbox=changed_outbox)

    first = project_service_before_replacement_occurrence(source)
    second = project_service_before_replacement_occurrence(changed)

    assert first.status is ServiceBeforeReplacementProjectionStatus.TERMINAL
    assert second.status is ServiceBeforeReplacementProjectionStatus.TERMINAL
    assert first.fingerprint != second.fingerprint


def test_projection_fingerprint_covers_service_proof_and_current_step_facts():
    source = _input()
    changed_proof = AuthoritativeActualServiceProof(
        case_no=source.lineage.case_no,
        service_dates=(),
        source_identity="scheduling-official-service:CASE-RPRE-001:other-source",
        source_version=4,
    )
    changed = replace(source, actual_service_proof=changed_proof)

    first = project_service_before_replacement_occurrence(source)
    second = project_service_before_replacement_occurrence(changed)

    assert first.status is ServiceBeforeReplacementProjectionStatus.TERMINAL
    assert second.status is ServiceBeforeReplacementProjectionStatus.TERMINAL
    assert first.fingerprint != second.fingerprint


def test_required_scenario_root_kind_cardinality_is_fail_closed():
    source = _input()
    roots = tuple(
        replace(root, root_kind="willingness")
        if root.root_kind.value == "candidate_binding"
        else root
        for root in source.roots
    )
    projection = project_service_before_replacement_occurrence(replace(source, roots=roots))

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.error_code == "replacement_root_kind_cardinality_invalid"


@pytest.mark.parametrize(
    "scenario, owner, extra_kind",
    [
        (ReplacementScenario.R01, "matching", "matching_plan"),
        (ReplacementScenario.R02, "matching", "candidate_binding"),
        (ReplacementScenario.R03, "matching", "matching_plan"),
        (ReplacementScenario.R04, "scheduling", "waiting_lock"),
    ],
)
def test_non_required_superseded_root_is_unknown_even_when_receipt_matches(
    scenario, owner, extra_kind
):
    source = _input(scenario=scenario)
    extra = ReplacementRootReadback(
        f"extra-superseded:{source.lineage.case_no}:old",
        owner,
        extra_kind,
        "superseded",
        False,
        source.lineage.case_no,
    )
    roots = source.roots + (extra,)
    superseded_ids = tuple(
        sorted(root.root_identity for root in roots if root.disposition == "superseded")
    )
    receipt = replace(
        source.receipt,
        superseded_root_ids=superseded_ids,
        superseded_root_set_digest=_digest(superseded_ids),
        superseded_root_count=len(superseded_ids),
    )

    projection = project_service_before_replacement_occurrence(
        replace(source, roots=roots, receipt=receipt)
    )

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.error_code == "replacement_root_kind_cardinality_invalid"


@pytest.mark.parametrize("scenario", tuple(ReplacementScenario)[:-1])
def test_extra_created_root_is_unknown_even_when_receipt_matches(scenario):
    source = _input(scenario=scenario)
    extra = ReplacementRootReadback(
        f"extra-created:{source.lineage.case_no}:9",
        "matching",
        "matching_plan",
        "created",
        False,
        source.lineage.case_no,
    )
    roots = source.roots + (extra,)
    created_ids = tuple(
        sorted(root.root_identity for root in roots if root.disposition == "created")
    )
    receipt = replace(
        source.receipt,
        created_root_ids=created_ids,
        created_root_set_digest=_digest(created_ids),
        created_root_count=len(created_ids),
    )

    projection = project_service_before_replacement_occurrence(
        replace(source, roots=roots, receipt=receipt)
    )

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.error_code == "replacement_successor_root_mismatch"


@pytest.mark.parametrize("scenario", tuple(ReplacementScenario)[:-1])
def test_current_retained_root_is_unknown_even_when_not_caregiver_bound(scenario):
    source = _input(scenario=scenario)
    extra = ReplacementRootReadback(
        f"extra-retained:{source.lineage.case_no}:current",
        "matching",
        "matching_plan",
        "retained",
        True,
        source.lineage.case_no,
        caregiver_bound=False,
    )
    roots = source.roots + (extra,)
    retained_ids = tuple(
        sorted(root.root_identity for root in roots if root.disposition == "retained")
    )
    receipt = replace(
        source.receipt,
        retained_root_ids=retained_ids,
        retained_root_set_digest=_digest(retained_ids),
        retained_root_count=len(retained_ids),
    )

    projection = project_service_before_replacement_occurrence(
        replace(source, roots=roots, receipt=receipt)
    )

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.error_code == "replacement_old_caregiver_root_still_current"


def _reuse_proof(*, accepted=False, same_round=True, case_no="CASE-RPRE-001"):
    return CandidatePoolReuseProof(
        pool_identity="candidate-pool:CASE-RPRE-001:9",
        round_identity="successor-round:CASE-RPRE-001:9",
        coverage_version=4,
        availability_version=5,
        willingness_version=6,
        fingerprint=fingerprint_payload({"pool": 1}),
        same_round=same_round,
        coverage_valid=True,
        availability_valid=True,
        willingness_valid=True,
        fresh=True,
        accepted_candidate=accepted,
        case_no=case_no,
        successor_round_identity="successor-round:CASE-RPRE-001:9",
        generation_version=8,
        event_version=8,
        candidate_identity="candidate:CASE-RPRE-001:1",
    )


@pytest.mark.parametrize("current_step, accepted", [(3, False), (4, True)])
def test_step_three_and_four_require_complete_fresh_candidate_pool_reuse_proof(current_step, accepted):
    source = _input(current_step=current_step)
    successor = replace(
        source.successor,
        resume_step=f"step_{current_step}",
        candidate_pool_reuse_proof=_reuse_proof(accepted=accepted),
    )
    source = replace(source, successor=successor)

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.TERMINAL


def test_projection_fingerprint_covers_candidate_pool_reuse_versions_and_flags():
    source = _input(current_step=3)
    successor = replace(
        source.successor,
        resume_step="step_3",
        candidate_pool_reuse_proof=_reuse_proof(),
    )
    source = replace(source, successor=successor)
    changed_proof = replace(
        successor.candidate_pool_reuse_proof,
        availability_version=99,
    )
    changed = replace(source, successor=replace(successor, candidate_pool_reuse_proof=changed_proof))

    first = project_service_before_replacement_occurrence(source)
    second = project_service_before_replacement_occurrence(changed)

    assert first.status is ServiceBeforeReplacementProjectionStatus.TERMINAL
    assert second.status is ServiceBeforeReplacementProjectionStatus.TERMINAL
    assert first.fingerprint != second.fingerprint


@pytest.mark.parametrize(
    "proof",
    [
        None,
        _reuse_proof(same_round=False),
        _reuse_proof(case_no="OTHER-CASE"),
    ],
)
def test_step_three_without_complete_same_round_case_bound_reuse_proof_is_unknown(proof):
    source = _input(current_step=3)
    successor = replace(
        source.successor,
        resume_step="step_3",
        candidate_pool_reuse_proof=proof,
    )
    source = replace(source, successor=successor)

    projection = project_service_before_replacement_occurrence(source)

    assert projection.status is ServiceBeforeReplacementProjectionStatus.OUTCOME_UNKNOWN
    assert projection.error_code == "replacement_candidate_pool_reuse_unavailable"

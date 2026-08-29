"""
File: test_historical_operational_baseline.py
Description: 驗證歷史作業基準候選、步驟投影與 replay 負向契約。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from domains.orders.historical_operational_baseline import (
    HistoricalBaselineLineage,
    HistoricalBaselineEvidenceMode,
    HistoricalBaselineInvalidationEvent,
    HistoricalBaselineOwnerRoot,
    HISTORICAL_BASELINE_CATALOG_VERSION,
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG,
    HistoricalBaselineStepState,
    HistoricalOperationalBaselineError,
    HistoricalOperationalBaselineFacts,
    HistoricalOperationalBaselineRequest,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
    baseline_payload_equivalent,
    build_historical_operational_baseline_candidate,
    build_historical_baseline_owner_root_vector,
    historical_baseline_owner_binding_fingerprint,
    project_earliest_invalidated_root,
    validate_historical_baseline_owner_catalog,
)
from shared_kernel.fingerprints import PreviewFingerprint


def _fingerprint(character: str = "a") -> PreviewFingerprint:
    return PreviewFingerprint(character * 64)


def _identity() -> HistoricalOrderIdentity:
    return HistoricalOrderIdentity("order:CASE-1", "CASE-1")


def _provenance(*, event: str = "historical-adoption:CASE-1", version: int = 2):
    return HistoricalOrderProvenanceIdentity(event, version)


def _facts(*, identity=None, version: int = 4, binding=None, provenance=None, prior_baseline_lineage=None):
    return HistoricalOperationalBaselineFacts(
        identity or _identity(), provenance or _provenance(), version,
        binding or _fingerprint(), prior_baseline_lineage
    )


def _request(
    *,
    identity=None,
    step: int = 8,
    version: int = 4,
    binding=None,
    mode=HistoricalBaselineEvidenceMode.RETAINED,
    reason: str = "歷史人工核對",
    evidence_reference: str = "evidence:CASE-1",
    document_kind: str | None = None,
    affected_steps: tuple[int, ...] | None = None,
):
    return HistoricalOperationalBaselineRequest(
        identity or _identity(),
        step,
        version,
        binding or _fingerprint(),
        mode,
        reason,
        evidence_reference,
        document_kind,
        affected_steps,
    )


def _candidate(**kwargs):
    facts = kwargs.pop("facts", _facts())
    request = kwargs.pop("request", None)
    if kwargs:
        request = _request(**kwargs)
    return build_historical_operational_baseline_candidate(facts, request or _request())


def _owner_roots(*, terminal_step: int | None = None, unavailable_step: int | None = None):
    roots = []
    for contract in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG:
        is_unavailable = contract.step == unavailable_step
        roots.append(
            HistoricalBaselineOwnerRoot(
                contract.contract_id,
                contract.contract_version,
                contract.step,
                contract.owner_domain,
                contract.root_identity_kind,
                contract.root_identity_path,
                contract.terminal_predicate_id,
                contract.terminal_predicate_version,
                contract.repair_target,
                contract.repair_capability,
                f"{contract.root_identity_kind}:CASE-1" if not is_unavailable else None,
                f"root-event:{contract.step}:CASE-1" if not is_unavailable else None,
                contract.step if not is_unavailable else None,
                None if is_unavailable else contract.step != terminal_step,
                "historical evidence unavailable" if is_unavailable else None,
                "CASE-1",
            )
        )
    return tuple(roots)


def test_step_eight_projects_only_prior_steps_and_current_step() -> None:
    candidate = _candidate()

    assert len(candidate.step_projection) == 8
    assert [item.step for item in candidate.step_projection] == list(range(1, 9))
    assert all(
        item.state is HistoricalBaselineStepState.HISTORICAL_BASELINE_COMPLETED
        for item in candidate.step_projection[:7]
    )
    assert (
        candidate.step_projection[-1].state
        is HistoricalBaselineStepState.IN_PROGRESS
    )


def test_candidate_is_actor_independent_and_fingerprint_is_deterministic() -> None:
    first = _candidate()
    second = _candidate()

    assert first.fingerprint == second.fingerprint
    assert baseline_payload_equivalent(first, second)
    assert "actor" not in first.canonical_payload


def test_unavailable_evidence_uses_separate_reason_and_reference() -> None:
    candidate = _candidate(
        mode=HistoricalBaselineEvidenceMode.UNAVAILABLE_ACCEPTED,
        reason="原始文件確實不可取得",
        evidence_reference="incident:HOB-1",
        document_kind="signed-contract",
        affected_steps=(6, 8),
    )

    assert (
        candidate.evidence_mode
        is HistoricalBaselineEvidenceMode.UNAVAILABLE_ACCEPTED
    )
    assert candidate.reason != candidate.evidence_reference
    assert candidate.canonical_payload["evidence_reference"] == "incident:HOB-1"
    assert candidate.canonical_payload["document_kind"] == "signed-contract"
    assert candidate.canonical_payload["affected_steps"] == (6, 8)


@pytest.mark.parametrize("step", [0, 12, True, "8"])
def test_step_must_be_integer_in_the_formal_eleven_step_range(step) -> None:
    with pytest.raises(HistoricalOperationalBaselineError) as raised:
        _request(step=step)

    assert raised.value.code in {
        "historical_baseline_step_invalid",
        "historical_baseline_step_out_of_range",
    }


def test_missing_historical_provenance_is_rejected() -> None:
    with pytest.raises(TypeError, match="historical provenance identity is required"):
        HistoricalOperationalBaselineFacts(_identity(), None, 4, _fingerprint())


def test_stale_expected_version_is_rejected() -> None:
    with pytest.raises(HistoricalOperationalBaselineError) as raised:
        _candidate(request=_request(version=3))

    assert raised.value.code == "historical_baseline_stale"


def test_expected_version_ahead_of_current_is_rejected_as_rollback() -> None:
    with pytest.raises(HistoricalOperationalBaselineError) as raised:
        _candidate(request=_request(version=5))

    assert raised.value.code == "historical_baseline_version_rollback"


def test_prior_lineage_rejects_step_regression_and_same_version_binding_drift() -> None:
    prior = HistoricalBaselineLineage(
        "baseline:event:1", _identity(), 8, 4, _fingerprint()
    )
    with pytest.raises(HistoricalOperationalBaselineError) as step_error:
        _candidate(
            facts=_facts(prior_baseline_lineage=prior),
            step=7,
        )
    assert step_error.value.code == "historical_baseline_step_regression"

    with pytest.raises(HistoricalOperationalBaselineError) as binding_error:
        _candidate(
            facts=_facts(prior_baseline_lineage=prior, binding=_fingerprint("b")),
            binding=_fingerprint("b"),
        )
    assert binding_error.value.code == "historical_baseline_prior_binding_conflict"

    other_prior = HistoricalBaselineLineage(
        "baseline:event:other", HistoricalOrderIdentity("order:CASE-2", "CASE-2"), 8, 4, _fingerprint()
    )
    with pytest.raises(HistoricalOperationalBaselineError) as identity_error:
        _candidate(facts=_facts(prior_baseline_lineage=other_prior))
    assert identity_error.value.code == "historical_baseline_prior_identity_mismatch"


def test_prior_lineage_allows_higher_version_successor_progression() -> None:
    prior = HistoricalBaselineLineage(
        "baseline:event:1", _identity(), 8, 4, _fingerprint()
    )
    candidate = _candidate(
        facts=_facts(
            version=5,
            binding=_fingerprint("b"),
            prior_baseline_lineage=prior,
        ),
        version=5,
        binding=_fingerprint("b"),
        step=9,
    )
    assert candidate.selected_step == 9
    assert candidate.prior_baseline_lineage == prior


def test_missing_reason_or_evidence_reference_is_rejected() -> None:
    with pytest.raises(ValueError, match="baseline reason"):
        _request(reason=" ")
    with pytest.raises(ValueError, match="baseline evidence reference"):
        _request(evidence_reference=" ")


def test_unavailable_evidence_requires_document_kind_and_affected_steps() -> None:
    with pytest.raises(HistoricalOperationalBaselineError) as missing_kind:
        _request(
            mode=HistoricalBaselineEvidenceMode.UNAVAILABLE_ACCEPTED,
            document_kind=None,
            affected_steps=(6,),
        )
    assert missing_kind.value.code == "historical_baseline_document_kind_required"

    with pytest.raises(HistoricalOperationalBaselineError) as missing_steps:
        _request(
            mode=HistoricalBaselineEvidenceMode.UNAVAILABLE_ACCEPTED,
            document_kind="signed-contract",
        )
    assert missing_steps.value.code == "historical_baseline_affected_steps_required"

    with pytest.raises(HistoricalOperationalBaselineError) as retained_details:
        _request(document_kind="signed-contract", affected_steps=(6,))
    assert retained_details.value.code == "historical_baseline_unavailable_evidence_fields_invalid"


def test_identity_and_binding_drift_are_rejected() -> None:
    other_identity = HistoricalOrderIdentity("order:CASE-2", "CASE-2")
    with pytest.raises(HistoricalOperationalBaselineError) as identity_error:
        _candidate(request=_request(identity=other_identity))
    assert identity_error.value.code == "historical_baseline_identity_mismatch"

    with pytest.raises(HistoricalOperationalBaselineError) as binding_error:
        _candidate(request=_request(binding=_fingerprint("b")))
    assert binding_error.value.code == "historical_baseline_binding_drift"


def test_different_evidence_payload_is_not_a_replay() -> None:
    first = _candidate()
    different = _candidate(request=_request(evidence_reference="evidence:other"))

    assert not baseline_payload_equivalent(first, different)
    assert first.fingerprint != different.fingerprint


def test_candidate_rejects_fabricated_projection_or_version() -> None:
    candidate = _candidate()

    with pytest.raises(HistoricalOperationalBaselineError):
        replace(
            candidate,
            current_orders_version=5,
            expected_orders_version=4,
        )
    with pytest.raises(HistoricalOperationalBaselineError):
        replace(candidate, step_projection=candidate.step_projection[:-1])
    with pytest.raises(HistoricalOperationalBaselineError) as fingerprint_error:
        replace(candidate, fingerprint=_fingerprint("f"))
    assert fingerprint_error.value.code == "historical_baseline_fingerprint_mismatch"


def test_owner_catalog_and_vector_all_complete_are_typed_and_ordered() -> None:
    vector = build_historical_baseline_owner_root_vector(
        tuple(reversed(_owner_roots())) , identity=_identity()
    )

    assert len(HISTORICAL_BASELINE_OWNER_ROOT_CATALOG) == 11
    assert [root.step for root in vector] == list(range(1, 12))
    assert project_earliest_invalidated_root(vector) is None
    assert all(entry.source_event_identity for entry in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG)
    assert all(entry.source_version == 1 for entry in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG)
    assert all(entry.repair_target == entry.owner_domain for entry in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG)


def test_catalog_and_projector_reject_unsupported_catalog_version() -> None:
    with pytest.raises(HistoricalOperationalBaselineError) as catalog_error:
        validate_historical_baseline_owner_catalog(catalog_version=2)
    assert catalog_error.value.code == "historical_baseline_catalog_version_unsupported"

    with pytest.raises(HistoricalOperationalBaselineError) as vector_error:
        build_historical_baseline_owner_root_vector(_owner_roots(), catalog_version=2)
    assert vector_error.value.code == "historical_baseline_catalog_version_unsupported"


def test_projector_path_requires_a_complete_vector_when_catalog_version_is_supplied() -> None:
    with pytest.raises(HistoricalOperationalBaselineError) as raised:
        HistoricalOperationalBaselineFacts(
            _identity(), _provenance(), 4, _fingerprint(), catalog_version=1
        )
    assert raised.value.code == "historical_baseline_owner_root_vector_required"


def test_unavailable_root_cannot_claim_terminal_or_carry_fabricated_facts() -> None:
    contract = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG[0]
    with pytest.raises(HistoricalOperationalBaselineError) as terminal_error:
        HistoricalBaselineOwnerRoot(
            contract.contract_id, contract.contract_version, contract.step,
            contract.owner_domain, contract.root_identity_kind, contract.root_identity_path,
            contract.terminal_predicate_id, contract.terminal_predicate_version,
            contract.repair_target, contract.repair_capability,
            "order:CASE-1", "event:CASE-1", 1, True,
            "historical evidence unavailable", "CASE-1",
        )
    assert terminal_error.value.code == "historical_baseline_owner_root_availability_inconsistent"

    with pytest.raises(HistoricalOperationalBaselineError) as available_error:
        HistoricalBaselineOwnerRoot(
            contract.contract_id, contract.contract_version, contract.step,
            contract.owner_domain, contract.root_identity_kind, contract.root_identity_path,
            contract.terminal_predicate_id, contract.terminal_predicate_version,
            contract.repair_target, contract.repair_capability,
            None, None, None, False, None, "CASE-1",
        )
    assert available_error.value.code == "historical_baseline_owner_root_fact_missing"


def test_h06_invalidation_event_binds_case_catalog_source_and_exact_set() -> None:
    vector = build_historical_baseline_owner_root_vector(_owner_roots(), identity=_identity())
    event = HistoricalBaselineInvalidationEvent(
        _identity(), 1, "orders:reopen:CASE-1", 99, (3, 7)
    )
    assert project_earliest_invalidated_root(
        vector,
        invalidation_event=event,
        identity=_identity(),
    ) == 3

    with pytest.raises(HistoricalOperationalBaselineError) as case_error:
        project_earliest_invalidated_root(
            vector,
            invalidation_event=HistoricalBaselineInvalidationEvent(
                HistoricalOrderIdentity("order:CASE-2", "CASE-2"),
                1, "orders:reopen:CASE-2", 99, (3,)
            ),
            identity=_identity(),
        )
    assert case_error.value.code == "historical_baseline_invalidation_identity_mismatch"

    with pytest.raises(HistoricalOperationalBaselineError) as set_error:
        HistoricalBaselineInvalidationEvent(_identity(), 1, "orders:reopen:CASE-1", 99, (3, 3))
    assert set_error.value.code == "historical_baseline_invalidation_set_invalid"


def test_owner_vector_missing_entry_fails_closed() -> None:
    with pytest.raises(HistoricalOperationalBaselineError) as raised:
        build_historical_baseline_owner_root_vector(_owner_roots()[:-1], identity=_identity())

    assert raised.value.code == "historical_baseline_owner_root_vector_incomplete"


def test_owner_vector_unavailable_is_not_treated_as_terminal() -> None:
    vector = build_historical_baseline_owner_root_vector(
        _owner_roots(unavailable_step=3), identity=_identity()
    )

    assert vector[2].available is False
    assert vector[2].terminal_result is None
    assert project_earliest_invalidated_root(vector) == 3


def test_whole_vector_fingerprint_is_permutation_stable() -> None:
    roots = _owner_roots()
    first = historical_baseline_owner_binding_fingerprint(_identity(), _provenance(), roots)
    second = historical_baseline_owner_binding_fingerprint(
        _identity(), _provenance(), tuple(reversed(roots))
    )

    assert first == second


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("cross_case", "historical_baseline_owner_root_cross_case"),
        ("duplicate", "historical_baseline_owner_root_duplicate"),
        ("unsupported", "historical_baseline_owner_root_contract_unsupported"),
        ("version", "historical_baseline_owner_root_contract_unsupported"),
    ],
)
def test_owner_vector_rejects_cross_case_duplicate_unsupported_and_version(
    mutation: str, code: str
) -> None:
    roots = list(_owner_roots())
    if mutation == "cross_case":
        roots[0] = replace(roots[0], case_no="CASE-2")
    elif mutation == "duplicate":
        roots[-1] = replace(roots[-1], step=1)
    elif mutation == "unsupported":
        roots[0] = replace(roots[0], terminal_predicate_id="predicate:unknown")
    else:
        roots[0] = replace(roots[0], contract_version=2)

    with pytest.raises(HistoricalOperationalBaselineError) as raised:
        build_historical_baseline_owner_root_vector(roots, identity=_identity())

    assert raised.value.code == code


def test_earliest_invalidated_root_uses_server_order_not_input_order() -> None:
    roots = _owner_roots()
    invalidated = replace(roots[7], terminal_result=False)
    invalidated_earlier = replace(roots[4], terminal_result=False)

    vector = build_historical_baseline_owner_root_vector(
        (invalidated, invalidated_earlier, *roots[:4], *roots[5:7], roots[8], *roots[9:]),
        identity=_identity(),
    )
    assert project_earliest_invalidated_root(vector) == 5


def test_h06_invalidation_event_requires_exact_order_and_case_identity() -> None:
    roots = _owner_roots()
    event = HistoricalBaselineInvalidationEvent(
        identity=HistoricalOrderIdentity("order:other", "CASE-1"),
        catalog_version=HISTORICAL_BASELINE_CATALOG_VERSION,
        source_event_identity="orders:reopened:2",
        source_version=99,
        invalidated_steps=(3,),
    )

    with pytest.raises(HistoricalOperationalBaselineError) as raised:
        project_earliest_invalidated_root(
            roots,
            invalidation_event=event,
            identity=_identity(),
        )

    assert raised.value.code == "historical_baseline_invalidation_identity_mismatch"


def test_candidate_keeps_baseline_selected_step_and_exposes_current_root_projection() -> None:
    roots = _owner_roots(terminal_step=8)
    binding = historical_baseline_owner_binding_fingerprint(_identity(), _provenance(), roots)
    facts = HistoricalOperationalBaselineFacts(
        _identity(), _provenance(), 4, binding, None, roots
    )
    candidate = _candidate(
        facts=facts,
        request=_request(step=11, binding=binding),
    )

    assert candidate.selected_step == 11
    assert candidate.current_step == 8
    assert candidate.earliest_invalidated_root == 8
    assert candidate.catalog_version == 1

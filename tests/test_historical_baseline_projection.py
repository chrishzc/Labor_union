"""
File: test_historical_baseline_projection.py
Description: 驗證 HCAT occurrence、umbrella、successor、terminal 與重播投影契約。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import random

import pytest

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
)
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.anomalies.historical_baseline_projection import (
    FreshHistoricalBaselineOwnerVectorReadback,
    HistoricalBaselineProjectionError,
    HistoricalBaselineProjectionSourceIntent,
    historical_baseline_catalog_identity,
    project_historical_baseline,
)
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerObservationReadback,
    HistoricalBaselineOwnerVectorV2Query,
    HistoricalBaselineOwnerVectorV2QueryRequest,
)


_IDENTITY = HistoricalOrderIdentity("order:CASE-HCAT-1", "CASE-HCAT-1")
_PROVENANCE = HistoricalOrderProvenanceIdentity("import:CASE-HCAT-1", 9)


@dataclass
class _Port:
    observations: dict[str, tuple[HistoricalBaselineOwnerObservation, ...]]
    owner_domain: str

    def read_owner_observations(self, identity, descriptor, *, for_update=False):
        return HistoricalBaselineOwnerObservationReadback(
            identity, self.observations[descriptor.contract_id]
        )


def _observation(descriptor, *, terminal=True, version=1, unavailable=None):
    if unavailable is not None:
        return HistoricalBaselineOwnerObservation.unavailable(
            descriptor, code=unavailable, case_no=_IDENTITY.case_no
        )
    return HistoricalBaselineOwnerObservation(
        descriptor=descriptor,
        root_identity=f"{descriptor.root_identity_kind}:{_IDENTITY.case_no}",
        source_event_identity=f"{descriptor.owner_domain}:event:{descriptor.contract_id}:v{version}",
        source_version=version,
        terminal_result=terminal,
        case_no=_IDENTITY.case_no,
    )


def _projection(states=None):
    states = states or {}
    observations = {}
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2:
        state = states.get(descriptor.contract_id, {})
        observations[descriptor.contract_id] = (
            _observation(
                descriptor,
                terminal=state.get("terminal", True),
                version=state.get("version", 1),
                unavailable=state.get("unavailable"),
            ),
        )
    ports = {
        owner: _Port(
            {
                descriptor.contract_id: observations[descriptor.contract_id]
                for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
                if descriptor.owner_domain == owner
            },
            owner,
        )
        for owner in {
            descriptor.owner_domain
            for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
        }
    }
    return HistoricalBaselineOwnerVectorV2Query.from_ports(ports).query(
        HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE)
    )


def _intent(projection):
    return HistoricalBaselineProjectionSourceIntent(
        source_intent_key="hcat.case-hcat-1.baseline-1",
        idempotency_key="hcat.case-hcat-1.projector-1",
        baseline_event_identity="baseline-event:CASE-HCAT-1:1",
        baseline_receipt_identity="baseline-receipt:CASE-HCAT-1:1",
        baseline_outbox_identity="baseline-outbox:CASE-HCAT-1:1",
        identity=_IDENTITY,
        selected_step=11,
        catalog_identity=historical_baseline_catalog_identity(),
        catalog_version=2,
        expected_owner_binding_fingerprint=projection.owner_binding_fingerprint,
    )


def _project(projection, prior=()):
    return project_historical_baseline(
        _intent(projection),
        FreshHistoricalBaselineOwnerVectorReadback(projection),
        prior_active_occurrences=prior,
    )


def test_all_terminal_vector_has_zero_active_occurrences_and_complete_receipt():
    result = _project(_projection())

    assert result.occurrences == ()
    assert result.successor_occurrences == ()
    assert result.umbrella.membership_count == 0
    assert result.umbrella.active is False
    assert result.terminal_conjunction is True
    assert result.current_step == 11
    assert result.baseline_selected_step == 11
    assert result.receipt.occurrence_set_count == 0
    assert result.receipt.result_state == "projected"
    assert result.outbox.payload["terminal_conjunction"] is True


def test_three_invalid_observations_have_exact_independent_memberships():
    descriptors = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[:3]
    projection = _projection(
        {
            descriptor.contract_id: {"terminal": False, "version": 1}
            for descriptor in descriptors
        }
    )
    result = _project(projection)

    assert len(result.occurrences) == 3
    assert len({item.occurrence_identity for item in result.occurrences}) == 3
    assert all(item.active and not item.terminal for item in result.occurrences)
    assert result.umbrella.membership_count == 3
    assert result.umbrella.membership_occurrence_identities == tuple(
        sorted(item.occurrence_identity for item in result.occurrences)
    )
    assert tuple(item.set_ordinal for item in result.umbrella.memberships) == (1, 2, 3)
    assert tuple(
        item.occurrence_identity for item in result.umbrella.memberships
    ) == result.umbrella.membership_occurrence_identities
    assert len({item.membership_identity for item in result.umbrella.memberships}) == 3
    assert result.current_step == min(item.step for item in descriptors)
    assert result.terminal_conjunction is False


def test_fresh_owner_terminal_successors_reduce_membership_three_two_one_zero():
    descriptors = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[:3]
    prior = ()
    counts = []
    for repaired_count in range(4):
        states = {
            descriptor.contract_id: {
                "terminal": index < repaired_count,
                "version": 2 if index < repaired_count else 1,
            }
            for index, descriptor in enumerate(descriptors)
        }
        result = _project(_projection(states), prior)
        counts.append(result.umbrella.membership_count)
        if repaired_count:
            assert len(result.successors) == 1
            assert len(result.successor_occurrences) == 1
            assert result.successor_occurrences[0].terminal is True
            assert result.successor_occurrences[0].active is False
            assert len(result.inactive_predecessor_identities) == 1
        prior = result.occurrences

    assert counts == [3, 2, 1, 0]
    assert result.terminal_conjunction is True


def test_successor_requires_same_lineage_strictly_newer_terminal_owner_fact():
    descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    before = _project(
        _projection({descriptor.contract_id: {"terminal": False, "version": 2}})
    )
    non_newer = _projection(
        {descriptor.contract_id: {"terminal": True, "version": 2}}
    )
    with pytest.raises(HistoricalBaselineProjectionError) as error:
        _project(non_newer, before.occurrences)
    assert error.value.code == "projector_successor_source_version_not_newer"

    still_false = _projection(
        {descriptor.contract_id: {"terminal": False, "version": 3}}
    )
    with pytest.raises(HistoricalBaselineProjectionError) as error:
        _project(still_false, before.occurrences)
    assert error.value.code == "projector_successor_not_terminal"


def test_typed_unavailable_is_active_and_only_fresh_terminal_conjunction_clears_it():
    descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    unavailable = _project(
        _projection(
            {descriptor.contract_id: {"unavailable": "owner_read_unavailable"}}
        )
    )
    assert unavailable.umbrella.membership_count == 1
    assert unavailable.occurrences[0].observation.source_version is None
    assert unavailable.terminal_conjunction is False

    repaired = _project(
        _projection({descriptor.contract_id: {"terminal": True, "version": 1}}),
        unavailable.occurrences,
    )
    assert repaired.umbrella.membership_count == 0
    assert repaired.inactive_predecessor_identities == (
        unavailable.occurrences[0].occurrence_identity,
    )
    assert repaired.successors == ()
    assert repaired.terminal_conjunction is True


def test_status_claim_or_receipt_cannot_replace_owner_terminal_readback():
    descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    projection = _projection(
        {descriptor.contract_id: {"terminal": False, "version": 4}}
    )
    result = _project(projection)

    assert result.terminal_conjunction is False
    assert result.occurrences[0].observation.terminal_result is False
    assert "status" not in result.outbox.payload
    assert "claim" not in result.outbox.payload
    assert result.receipt.result_state == "projected"


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (
            lambda projection: replace(
                projection, owner_collections=projection.owner_collections[:-1]
            ),
            "projector_owner_collections_partial",
        ),
        (
            lambda projection: replace(projection, current_step=1),
            "projector_current_step_readback_mismatch",
        ),
        (
            lambda projection: replace(
                projection,
                owner_binding_fingerprint=PreviewFingerprint("0" * 64),
            ),
            "projector_owner_vector_fingerprint_mismatch",
        ),
    ],
)
def test_partial_malformed_or_stale_vector_fails_closed(mutator, code):
    projection = _projection()
    tampered = mutator(projection)
    with pytest.raises(HistoricalBaselineProjectionError) as error:
        project_historical_baseline(
            replace(
                _intent(projection),
                expected_owner_binding_fingerprint=tampered.owner_binding_fingerprint,
            ),
            FreshHistoricalBaselineOwnerVectorReadback(tampered),
        )
    assert error.value.code == code


def test_cross_case_stale_and_unavailable_readback_fail_closed():
    projection = _projection()
    with pytest.raises(HistoricalBaselineProjectionError) as error:
        project_historical_baseline(
            replace(
                _intent(projection),
                identity=HistoricalOrderIdentity("order:OTHER", "OTHER"),
            ),
            FreshHistoricalBaselineOwnerVectorReadback(projection),
        )
    assert error.value.code == "projector_cross_case_or_order"

    with pytest.raises(HistoricalBaselineProjectionError) as error:
        project_historical_baseline(
            replace(
                _intent(projection),
                expected_owner_binding_fingerprint=PreviewFingerprint("f" * 64),
            ),
            FreshHistoricalBaselineOwnerVectorReadback(projection),
        )
    assert error.value.code == "projector_owner_binding_stale"

    with pytest.raises(HistoricalBaselineProjectionError) as error:
        project_historical_baseline(
            _intent(projection),
            FreshHistoricalBaselineOwnerVectorReadback(projection, fresh=False),
        )
    assert error.value.code == "projector_readback_unavailable"


@pytest.mark.parametrize(
    ("target", "field"),
    (
        ("observation", "root_identity"),
        ("observation", "source_version"),
        ("descriptor", "owner_domain"),
        ("descriptor", "terminal_predicate_id"),
    ),
)
def test_tampered_missing_owner_identity_version_or_predicate_fails_closed(
    target, field
):
    descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    projection = _projection(
        {descriptor.contract_id: {"terminal": False, "version": 1}}
    )
    observation = replace(projection.owner_observations[0])
    if target == "observation":
        object.__setattr__(observation, field, None)
    else:
        tampered_descriptor = replace(observation.descriptor)
        object.__setattr__(tampered_descriptor, field, "")
        object.__setattr__(observation, "descriptor", tampered_descriptor)
    projection = replace(
        projection,
        owner_observations=(observation, *projection.owner_observations[1:]),
    )
    with pytest.raises(HistoricalBaselineProjectionError) as error:
        _project(projection)
    assert error.value.code == "projector_owner_vector_malformed"


def test_prior_occurrence_cross_case_or_tampered_predicate_fails_closed():
    descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    before = _project(
        _projection({descriptor.contract_id: {"terminal": False, "version": 1}})
    )
    prior = before.occurrences[0]
    repaired = _projection(
        {descriptor.contract_id: {"terminal": True, "version": 2}}
    )

    with pytest.raises(HistoricalBaselineProjectionError) as error:
        _project(repaired, (replace(prior, case_no="OTHER"),))
    assert error.value.code == "projector_prior_occurrence_cross_case"

    tampered_descriptor = replace(
        prior.descriptor, terminal_predicate_id="tampered-predicate"
    )
    with pytest.raises(HistoricalBaselineProjectionError) as error:
        _project(repaired, (replace(prior, descriptor=tampered_descriptor),))
    assert error.value.code == "projector_prior_occurrence_malformed"


def test_projection_is_stable_across_owner_observation_permutations():
    descriptors = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[:5]
    base = _projection(
        {
            descriptor.contract_id: {"terminal": False, "version": 1}
            for descriptor in descriptors
        }
    )
    expected = _project(base)
    rng = random.Random(96)
    for _ in range(100):
        values = list(base.owner_observations)
        rng.shuffle(values)
        assert _project(replace(base, owner_observations=tuple(values))) == expected

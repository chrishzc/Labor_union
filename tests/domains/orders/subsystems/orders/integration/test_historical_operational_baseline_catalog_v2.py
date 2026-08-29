"""
File: test_historical_operational_baseline_catalog_v2.py
Description: 驗證歷史作業基準 catalog-v2 的多 descriptor、typed observation 與 fail-closed 契約。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HISTORICAL_BASELINE_CATALOG_VERSION_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalBaselineOwnerRootCollection,
    HistoricalBaselineOwnerRootDescriptor,
    HistoricalOperationalBaselineError,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
    build_historical_baseline_owner_root_vector_v2,
    historical_baseline_owner_binding_fingerprint_v2,
    project_earliest_invalidated_root_v2,
    validate_historical_baseline_owner_catalog_v2,
)


IDENTITY = HistoricalOrderIdentity("order:CASE-1", "CASE-1")
PROVENANCE = HistoricalOrderProvenanceIdentity("adoption:CASE-1", 3)


def _observation(descriptor, suffix: str, *, terminal: bool = True):
    return HistoricalBaselineOwnerObservation(
        descriptor=descriptor,
        root_identity=f"{descriptor.root_identity_kind}:CASE-1:{suffix}",
        source_event_identity=f"{descriptor.owner_domain}:event:{suffix}",
        source_version=3,
        terminal_result=terminal,
        case_no="CASE-1",
    )


def _complete_observations():
    observations = []
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2:
        observations.append(_observation(descriptor, descriptor.contract_id))
    return tuple(observations)


def test_v2_catalog_has_correct_multi_owner_map_and_typed_referrals():
    by_step = {}
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2:
        by_step.setdefault(descriptor.step, set()).add(descriptor.owner_domain)

    assert by_step[3] == {"matching"}
    assert by_step[5] == {"matching"}
    assert by_step[9] == {"scheduling"}
    effective_generation = next(
        descriptor
        for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
        if descriptor.step == 10 and descriptor.root_identity_kind == "effective_generation"
    )
    assert effective_generation.owner_domain == "scheduling"
    assert effective_generation.root_identity_path == "scheduling.effective_generation_identity"
    assert effective_generation.repair_target == "scheduling"
    assert effective_generation.repair_capability.startswith("scheduling.")
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2:
        if (descriptor.step, descriptor.root_identity_kind) in {
            (9, "confirmed_service_date"),
            (10, "assignment_official_date"),
            (11, "staff_payout"),
        }:
            assert descriptor.maximum_cardinality is None
    assert len(by_step[8]) > 1
    assert len(by_step[10]) > 1
    assert len(by_step[11]) > 1
    assert all(
        descriptor.repair_capability != "orders.historical_review.remediate"
        for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    )


@pytest.mark.parametrize("variant", ["missing", "extra", "unknown_owner", "drift"])
def test_v2_catalog_requires_the_canonical_descriptor_set_and_owner_map(variant):
    descriptors = list(HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2)
    if variant == "missing":
        descriptors.pop()
    elif variant == "extra":
        descriptors.append(replace(descriptors[0], contract_id="historical-baseline.v2.extra"))
    elif variant == "unknown_owner":
        descriptors[0] = replace(
            descriptors[0], owner_domain="unknown", repair_target="unknown"
        )
    else:
        descriptors[0] = replace(descriptors[0], step=2)

    with pytest.raises(HistoricalOperationalBaselineError):
        validate_historical_baseline_owner_catalog_v2(descriptors)


def test_v2_catalog_accepts_permutation_but_returns_canonical_order():
    shuffled = tuple(reversed(HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2))
    validated = validate_historical_baseline_owner_catalog_v2(shuffled)
    assert validated == tuple(
        sorted(shuffled, key=lambda item: (item.step, item.contract_id))
    )


def test_v2_allows_multi_descriptor_and_multi_observation_with_stable_order():
    descriptors = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    observations = list(_complete_observations())
    collection_descriptor = next(
        item for item in descriptors if item.step == 6
    )
    observations.extend(
        (
            _observation(collection_descriptor, "segment-b"),
            _observation(collection_descriptor, "segment-a"),
        )
    )
    first = build_historical_baseline_owner_root_vector_v2(
        observations, identity=IDENTITY
    )
    second = build_historical_baseline_owner_root_vector_v2(
        tuple(reversed(observations)), identity=IDENTITY
    )

    assert len(first) == len(observations)
    assert [item.canonical_order_key for item in first] == sorted(
        item.canonical_order_key for item in first
    )
    assert first == second
    assert historical_baseline_owner_binding_fingerprint_v2(
        IDENTITY, PROVENANCE, observations
    ) == historical_baseline_owner_binding_fingerprint_v2(
        IDENTITY, PROVENANCE, tuple(reversed(observations))
    )


def test_v2_vector_requires_explicit_historical_order_identity():
    with pytest.raises((TypeError, HistoricalOperationalBaselineError)):
        build_historical_baseline_owner_root_vector_v2(
            _complete_observations(), identity=None
        )


def test_v2_collection_predicate_requires_cardinality_and_all_required():
    descriptor = next(
        item
        for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
        if item.step == 6
    )
    assert descriptor.collection.all_required is True
    constrained = replace(
        descriptor,
        collection=replace(descriptor.collection, minimum_cardinality=2),
    )
    with pytest.raises(HistoricalOperationalBaselineError) as raised:
        HistoricalBaselineOwnerRootCollection(
            constrained,
            (_observation(constrained, "only"),),
        )
    assert raised.value.code == "historical_baseline_v2_collection_cardinality_invalid"


@pytest.mark.parametrize(
    "mutation",
    [
        {"all_required": False},
        {"required_root_identity_kinds": ()},
        {"required_root_identity_kinds": ("other",)},
    ],
)
def test_v2_collection_contract_requires_required_kind_and_all_required(mutation):
    descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    with pytest.raises(HistoricalOperationalBaselineError):
        invalid_collection = replace(descriptor.collection, **mutation)
        invalid_descriptor = replace(descriptor, collection=invalid_collection)
        observation = _observation(invalid_descriptor, "a")
        HistoricalBaselineOwnerRootCollection(invalid_descriptor, (observation,))


def test_v2_descriptor_requires_a_real_collection_object():
    descriptor = replace(HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0], collection=None)
    with pytest.raises(HistoricalOperationalBaselineError):
        validate_historical_baseline_owner_catalog_v2(
            [descriptor, *HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[1:]]
        )


@pytest.mark.parametrize("kind", ["duplicate", "cross_case", "version_drift"])
def test_v2_duplicate_cross_case_and_version_drift_fail_closed(kind):
    descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    first = _observation(descriptor, "same")
    if kind == "duplicate":
        second = first
    elif kind == "cross_case":
        second = replace(first, case_no="CASE-2")
    else:
        second = replace(first, source_version=4)
    with pytest.raises(HistoricalOperationalBaselineError) as raised:
        build_historical_baseline_owner_root_vector_v2(
            [first, second], identity=IDENTITY
        )
    assert raised.value.code in {
        "historical_baseline_v2_observation_duplicate",
        "historical_baseline_v2_cross_case",
        "historical_baseline_v2_source_version_drift",
    }


def test_v2_unavailable_observation_is_typed_and_never_terminal():
    descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    unavailable = HistoricalBaselineOwnerObservation.unavailable(
        descriptor, code="owner_read_unavailable", case_no="CASE-1"
    )
    observations = [
        unavailable,
        *(
            item
            for item in _complete_observations()
            if item.descriptor != descriptor
        ),
    ]
    vector = build_historical_baseline_owner_root_vector_v2(
        observations, identity=IDENTITY
    )
    assert vector[0].available is False
    assert unavailable.root_identity is None
    assert unavailable.source_event_identity is None
    assert unavailable.source_version is None
    assert unavailable.canonical_tuple[2:5] == (None, None, None)
    assert project_earliest_invalidated_root_v2(vector, identity=IDENTITY) == 1


def test_v2_observation_accepts_initial_zero_source_version_but_descriptor_does_not():
    descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    observation = _observation(descriptor, "initial", terminal=True)
    zero_version = replace(observation, source_version=0)
    assert zero_version.source_version == 0
    assert descriptor.source_version > 0
    with pytest.raises(ValueError):
        replace(descriptor, source_version=0)


def test_v2_collection_is_typed_and_v1_history_remains_separate():
    collection = HistoricalBaselineOwnerRootCollection(
        descriptor=HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0],
        observations=(_observation(HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0], "a"),),
    )
    assert collection.observations[0].available
    assert HISTORICAL_BASELINE_CATALOG_VERSION_V2 == 2

"""
File: test_historical_baseline_owner_vector.py
Description: 驗證歷史訂單 owner vector 的 fresh read、排序、fingerprint 與 fail-closed 邊界。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import random

import pytest

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG,
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalBaselineOwnerRoot,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
)
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerVectorError,
    HistoricalBaselineOwnerVectorQuery,
    HistoricalBaselineOwnerVectorQueryRequest,
    HistoricalBaselineOwnerVectorV2QueryRequest,
    HistoricalBaselineOwnerRootReadback,
    HistoricalBaselineOwnerObservationReadback,
    HistoricalBaselineOwnerVectorV2Query,
)


_IDENTITY = HistoricalOrderIdentity("order:CASE-1", "CASE-1")
_PROVENANCE = HistoricalOrderProvenanceIdentity("import:CASE-1", 4)


def _root(descriptor, *, case_no="CASE-1", terminal=True, unavailable=None):
    return HistoricalBaselineOwnerRoot(
        contract_id=descriptor.contract_id,
        contract_version=descriptor.contract_version,
        step=descriptor.step,
        owner_domain=descriptor.owner_domain,
        root_identity_kind=descriptor.root_identity_kind,
        root_identity_path=descriptor.root_identity_path,
        terminal_predicate_id=descriptor.terminal_predicate_id,
        terminal_predicate_version=descriptor.terminal_predicate_version,
        repair_target=descriptor.repair_target,
        repair_capability=descriptor.repair_capability,
        root_identity=None if unavailable else f"{descriptor.owner_domain}:root:{descriptor.step}",
        source_event_identity=None if unavailable else f"event:{descriptor.step}",
        source_version=None if unavailable else descriptor.step,
        terminal_result=None if unavailable else terminal,
        unavailable_reason=unavailable,
        case_no=case_no,
    )


@dataclass
class _Port:
    roots: dict[int, HistoricalBaselineOwnerRoot]
    owner_domain: str = ""

    def __post_init__(self):
        self.calls = []

    def read_owner_root(self, identity, descriptor, *, for_update=False):
        self.calls.append((identity, descriptor.step, for_update))
        return HistoricalBaselineOwnerRootReadback(identity, self.roots[descriptor.step])


def _ports(roots=None):
    roots = roots or {
        item.step: _root(item) for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG
    }
    return {
        owner: _Port({
            item.step: roots[item.step]
            for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG
            if item.owner_domain == owner
        }, owner_domain=owner)
        for owner in {item.owner_domain for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG}
    }


def _query(ports=None):
    return HistoricalBaselineOwnerVectorQuery.from_ports(ports or _ports())


def test_query_reads_each_descriptor_once_and_returns_complete_projection():
    ports = _ports()
    result = _query(ports).query(
        HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE)
    )

    assert result.identity == _IDENTITY
    assert result.catalog_version == 1
    assert [root.step for root in result.owner_root_vector] == list(range(1, 12))
    assert result.current_step == 11
    assert result.earliest_unavailable_step is None
    assert len(result.repair_referrals) == 11
    assert all(call[2] is False for port in ports.values() for call in port.calls)
    assert sum(len(port.calls) for port in ports.values()) == 11


def test_same_facts_are_permutation_stable_and_repair_referral_is_server_owned():
    ports = _ports()
    result = _query(ports).execute(
        HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE)
    )
    assert result.fingerprint == result.owner_binding_fingerprint
    assert result.repair_referrals[9].repair_target == "scheduling"
    assert result.repair_referrals[9].repair_capability == "orders.historical_review.remediate"


def test_unavailable_typed_root_returns_earliest_unavailable_and_current_step():
    roots = {item.step: _root(item) for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG}
    roots[3] = _root(HISTORICAL_BASELINE_OWNER_ROOT_CATALOG[2], unavailable="owner timeout")
    result = _query(_ports(roots)).query(
        HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE)
    )
    assert result.earliest_unavailable_step == 3
    assert result.current_step == 3
    assert result.owner_root_vector[2].available is False


def test_missing_or_extra_ports_fail_closed():
    ports = _ports()
    with pytest.raises(HistoricalBaselineOwnerVectorError) as missing:
        HistoricalBaselineOwnerVectorQuery.from_ports({key: value for key, value in ports.items() if key != "line"})
    assert missing.value.code.endswith("port_missing")
    with pytest.raises(HistoricalBaselineOwnerVectorError) as extra:
        HistoricalBaselineOwnerVectorQuery.from_ports({**ports, "unknown": _Port({})})
    assert extra.value.code.endswith("port_extra")
    with pytest.raises(HistoricalBaselineOwnerVectorError) as duplicate:
        HistoricalBaselineOwnerVectorQuery.from_ports(
            tuple(ports.items()) + (("orders", ports["orders"]),)
        )
    assert duplicate.value.code.endswith("port_duplicate")


def test_v1_factory_accepts_legal_iterable_pairs():
    result = HistoricalBaselineOwnerVectorQuery.from_ports(
        tuple(reversed(tuple(_ports().items())))
    ).query(HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE))
    assert result.catalog_version == 1


def test_malformed_none_cross_case_and_unsupported_root_fail_closed():
    roots = {item.step: _root(item) for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG}
    roots[1] = None
    with pytest.raises(HistoricalBaselineOwnerVectorError) as none_result:
        _query(_ports(roots)).query(HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE))
    assert none_result.value.code.endswith("result_unavailable")

    roots = {item.step: _root(item) for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG}
    roots[2] = _root(HISTORICAL_BASELINE_OWNER_ROOT_CATALOG[1], case_no="CASE-2")
    with pytest.raises(HistoricalBaselineOwnerVectorError) as cross_case:
        _query(_ports(roots)).query(HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE))
    assert cross_case.value.code.endswith("cross_case")

    roots = {item.step: _root(item) for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG}
    roots[4] = object()
    with pytest.raises(HistoricalBaselineOwnerVectorError) as malformed:
        _query(_ports(roots)).query(HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE))
    assert malformed.value.code.endswith("result_malformed")

    roots = {item.step: _root(item) for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG}
    roots[5] = replace(roots[5], contract_id="unsupported-contract")
    with pytest.raises(HistoricalBaselineOwnerVectorError) as unsupported:
        _query(_ports(roots)).query(HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE))
    assert unsupported.value.code.endswith("unsupported_descriptor")


def test_port_reader_failure_and_generic_resolve_are_not_accepted():
    class BadPort:
        def resolve(self, *_args, **_kwargs):
            return None

    ports = _ports()
    ports["orders"] = BadPort()
    with pytest.raises(HistoricalBaselineOwnerVectorError) as invalid:
        _query(ports)
    assert invalid.value.code.endswith("orders_port_invalid")

    class FailingPort(_Port):
        def read_owner_root(self, *args, **kwargs):
            raise RuntimeError("unavailable")

    ports = _ports()
    ports["orders"] = FailingPort(ports["orders"].roots, owner_domain="orders")
    with pytest.raises(HistoricalBaselineOwnerVectorError) as failed:
        _query(ports).query(HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE))
    assert failed.value.code.endswith("orders_read_failed")


def test_same_version_tampered_catalog_is_rejected():
    tampered = replace(
        HISTORICAL_BASELINE_OWNER_ROOT_CATALOG[0],
        root_identity_path="orders.tampered_identity",
    )
    with pytest.raises(HistoricalBaselineOwnerVectorError) as error:
        HistoricalBaselineOwnerVectorQuery.from_ports(
            _ports(),
            catalog=(tampered, *HISTORICAL_BASELINE_OWNER_ROOT_CATALOG[1:]),
            catalog_version=1,
        )
    assert error.value.code.endswith("catalog_invalid")


def test_one_port_cannot_prove_two_owner_domains():
    ports = _ports()
    ports["matching"] = ports["orders"]
    with pytest.raises(HistoricalBaselineOwnerVectorError) as error:
        HistoricalBaselineOwnerVectorQuery.from_ports(ports)
    assert error.value.code.endswith("matching_port_owner_invalid")


def test_root_readback_must_bind_full_order_identity():
    class WrongIdentityPort(_Port):
        def read_owner_root(self, identity, descriptor, *, for_update=False):
            return HistoricalBaselineOwnerRootReadback(
                HistoricalOrderIdentity(identity.order_identity + ":other", identity.case_no),
                self.roots[descriptor.step],
            )

    ports = _ports()
    ports["orders"] = WrongIdentityPort(ports["orders"].roots, owner_domain="orders")
    with pytest.raises(HistoricalBaselineOwnerVectorError) as error:
        _query(ports).query(HistoricalBaselineOwnerVectorQueryRequest(_IDENTITY, _PROVENANCE))
    assert error.value.code.endswith("identity_mismatch")


def _observation(descriptor, suffix: str, *, terminal: bool = True, case_no="CASE-1"):
    return HistoricalBaselineOwnerObservation(
        descriptor=descriptor,
        root_identity=f"{descriptor.root_identity_kind}:CASE-1:{suffix}",
        source_event_identity=f"{descriptor.owner_domain}:event:{suffix}",
        source_version=3,
        terminal_result=terminal,
        case_no=case_no,
    )


@dataclass
class _V2Port:
    observations: dict[str, tuple[HistoricalBaselineOwnerObservation, ...]]
    owner_domain: str

    def __post_init__(self):
        self.calls = []

    def read_owner_observations(self, identity, descriptor, *, for_update=False):
        self.calls.append((identity, descriptor.contract_id, for_update))
        return HistoricalBaselineOwnerObservationReadback(
            identity, self.observations[descriptor.contract_id]
        )


def _v2_ports(observations=None):
    observations = observations or {
        descriptor.contract_id: (_observation(descriptor, descriptor.contract_id),)
        for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    }
    return {
        owner: _V2Port(
            {
                descriptor.contract_id: observations.get(descriptor.contract_id, ())
                for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
                if descriptor.owner_domain == owner
            },
            owner,
        )
        for owner in {descriptor.owner_domain for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2}
    }


def test_v2_query_reads_all_21_descriptors_and_multi_observations_deterministically():
    observations = {
        descriptor.contract_id: (_observation(descriptor, descriptor.contract_id),)
        for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    }
    segment = next(
        descriptor for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
        if descriptor.step == 6
    )
    observations[segment.contract_id] = (
        _observation(segment, "b"),
        _observation(segment, "a"),
    )
    ports = _v2_ports(observations)
    query = HistoricalBaselineOwnerVectorV2Query.from_ports(ports)
    request = HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE)
    result = query.query(request)
    assert result.catalog_version == 2
    assert len(result.owner_observations) == 22
    assert [item.canonical_order_key for item in result.owner_observations] == sorted(
        item.canonical_order_key for item in result.owner_observations
    )
    step_six_collection = next(
        collection
        for collection in result.owner_collections
        if collection.descriptor.step == 6
    )
    assert [item.canonical_order_key for item in step_six_collection.observations] == sorted(
        item.canonical_order_key for item in step_six_collection.observations
    )
    assert result.current_step == 11
    assert len(result.repair_referrals) == 21
    assert all(
        len(port.calls) == sum(
            descriptor.owner_domain == port.owner_domain
            for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
        )
        for port in ports.values()
    )


def test_v2_projection_is_stable_across_random_port_and_observation_permutations():
    rng = random.Random(96)
    expected = None
    descriptors = tuple(HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2)
    for _ in range(100):
        observations = {
            descriptor.contract_id: [_observation(descriptor, descriptor.contract_id)]
            for descriptor in descriptors
        }
        segment = next(descriptor for descriptor in descriptors if descriptor.step == 6)
        observations[segment.contract_id].extend(
            (_observation(segment, "b"), _observation(segment, "a"))
        )
        for values in observations.values():
            rng.shuffle(values)
        ports = _v2_ports({key: tuple(value) for key, value in observations.items()})
        items = list(ports.items())
        rng.shuffle(items)
        result = HistoricalBaselineOwnerVectorV2Query.from_ports(items).query(
            HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE)
        )
        if expected is None:
            expected = result
        else:
            assert result == expected


def test_v2_query_typed_unavailable_sets_step_without_fake_terminal():
    unavailable_descriptor = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[2]
    observations = {
        descriptor.contract_id: (_observation(descriptor, descriptor.contract_id),)
        for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    }
    observations[unavailable_descriptor.contract_id] = (
        HistoricalBaselineOwnerObservation.unavailable(
            unavailable_descriptor,
            code="owner_read_unavailable",
            case_no="CASE-1",
        ),
    )
    result = HistoricalBaselineOwnerVectorV2Query.from_ports(
        _v2_ports(observations)
    ).query(HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE))
    assert result.earliest_unavailable_step == 3
    assert result.current_step == 3
    assert result.owner_observations[2].available is False


def test_compatibility_query_factory_switches_to_v2_without_touching_v1_api():
    result = HistoricalBaselineOwnerVectorQuery.from_ports(
        _v2_ports(), catalog=HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2, catalog_version=2
    ).query(HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE))
    assert result.catalog_version == 2
    assert len(result.owner_observations) == 21


def test_compatibility_query_factory_detects_v2_owner_set():
    result = HistoricalBaselineOwnerVectorQuery.from_ports(_v2_ports()).query(
        HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE)
    )
    assert result.catalog_version == 2


def test_compatibility_query_factory_detects_v2_owner_set_from_iterable_pairs():
    result = HistoricalBaselineOwnerVectorQuery.from_ports(
        tuple(reversed(tuple(_v2_ports().items())))
    ).query(HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE))
    assert result.catalog_version == 2


def test_v2_iterable_duplicate_and_unknown_owner_keys_fail_closed():
    ports = tuple(_v2_ports().items())
    with pytest.raises(HistoricalBaselineOwnerVectorError):
        HistoricalBaselineOwnerVectorQuery.from_ports(ports + (ports[0],))
    with pytest.raises(HistoricalBaselineOwnerVectorError):
        HistoricalBaselineOwnerVectorQuery.from_ports(
            ports + (("unknown", _v2_ports()["orders"]),)
        )


def test_v2_descriptor_catalog_defaults_to_v2_only_when_version_is_omitted():
    ports = _v2_ports()
    query = HistoricalBaselineOwnerVectorQuery(
        orders=ports["orders"],
        matching=ports["matching"],
        contract_signing=ports["contract_signing"],
        client_finance=ports["client_finance"],
        scheduling=ports["scheduling"],
        staff_payables=ports["staff_payables"],
        catalog=HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    )
    assert query.query(
        HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE)
    ).catalog_version == 2


def test_v2_descriptor_catalog_rejects_explicit_non_v2_version():
    ports = _v2_ports()
    with pytest.raises(HistoricalBaselineOwnerVectorError) as error:
        HistoricalBaselineOwnerVectorQuery(
            orders=ports["orders"],
            matching=ports["matching"],
            contract_signing=ports["contract_signing"],
            client_finance=ports["client_finance"],
            scheduling=ports["scheduling"],
            staff_payables=ports["staff_payables"],
            catalog=HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
            catalog_version=1,
        )
    assert error.value.code.endswith("v2_catalog_invalid")


def test_v2_request_is_distinct_and_defaults_to_v2():
    assert HistoricalBaselineOwnerVectorV2QueryRequest is not HistoricalBaselineOwnerVectorQueryRequest
    assert HistoricalBaselineOwnerVectorV2QueryRequest(
        _IDENTITY, _PROVENANCE
    ).catalog_version == 2


def test_v2_query_request_controls_lock_mode_for_every_owner_port():
    ports = _v2_ports()
    query = HistoricalBaselineOwnerVectorV2Query.from_ports(ports)

    query.query(HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE))
    assert all(call[2] is False for port in ports.values() for call in port.calls)

    for port in ports.values():
        port.calls.clear()
    query.query(
        HistoricalBaselineOwnerVectorV2QueryRequest(
            _IDENTITY, _PROVENANCE, for_update=True
        )
    )
    assert all(call[2] is True for port in ports.values() for call in port.calls)
    assert sum(len(port.calls) for port in ports.values()) == 21


def test_v2_request_rejects_non_boolean_lock_mode():
    with pytest.raises(HistoricalBaselineOwnerVectorError) as error:
        HistoricalBaselineOwnerVectorV2QueryRequest(
            _IDENTITY, _PROVENANCE, for_update=1
        )
    assert error.value.code.endswith("read_mode_invalid")


@pytest.mark.parametrize("failure", ["missing", "partial", "cross_case", "unsupported", "version_drift"])
def test_v2_query_fail_closed_for_collection_and_observation_drift(failure):
    observations = {
        descriptor.contract_id: [_observation(descriptor, descriptor.contract_id)]
        for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    }
    target = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[0]
    if failure == "missing":
        observations.pop(target.contract_id)
    elif failure == "partial":
        observations[target.contract_id] = []
    elif failure == "cross_case":
        observations[target.contract_id] = [_observation(target, "x", case_no="CASE-2")]
    elif failure == "unsupported":
        observations[target.contract_id] = [object()]
    else:
        observations[target.contract_id] = [
            _observation(target, "x"), _observation(target, "x", terminal=False)
        ]
    with pytest.raises(HistoricalBaselineOwnerVectorError) as error:
        HistoricalBaselineOwnerVectorV2Query.from_ports(
            _v2_ports({key: tuple(value) for key, value in observations.items()})
        ).query(HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE))
    assert error.value.code.startswith("historical_baseline_owner_vector_")

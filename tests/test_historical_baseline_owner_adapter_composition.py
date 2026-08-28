"""
File: test_historical_baseline_owner_adapter_composition.py
Description: 驗證六個 HCAT owner 共用借用連線、固定讀序與鎖定傳遞。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
    validate_historical_baseline_owner_catalog_v2,
)
from infrastructure.mysql import historical_baseline_owner_adapter_composition as composition
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerObservationReadback,
    HistoricalBaselineOwnerVectorError,
    HistoricalBaselineOwnerVectorV2Query,
    HistoricalBaselineOwnerVectorV2QueryRequest,
)


_IDENTITY = HistoricalOrderIdentity("order:HCAT-COMPOSITION-1", "HCAT-COMPOSITION-1")
_PROVENANCE = HistoricalOrderProvenanceIdentity("import:HCAT-COMPOSITION-1", 4)
_OWNER_NAMES = (
    "orders",
    "matching",
    "contract_signing",
    "client_finance",
    "scheduling",
    "staff_payables",
)
_READ_ORDER = validate_historical_baseline_owner_catalog_v2(
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
)


class _BorrowedConnection:
    def __init__(self) -> None:
        self.transaction_calls: list[str] = []

    def begin(self) -> None:
        self.transaction_calls.append("begin")

    def commit(self) -> None:
        self.transaction_calls.append("commit")

    def rollback(self) -> None:
        self.transaction_calls.append("rollback")

    def close(self) -> None:
        self.transaction_calls.append("close")


@dataclass
class _FakeOwnerPort:
    owner_domain: str
    connection: object
    calls: list[tuple[str, str, bool]]
    fail_on_contract_id: str | None = None

    def read_owner_observations(self, identity, descriptor, *, for_update=False):
        self.calls.append((self.owner_domain, descriptor.contract_id, for_update))
        if descriptor.contract_id == self.fail_on_contract_id:
            raise RuntimeError("owner read failed")
        observation = HistoricalBaselineOwnerObservation(
            descriptor=descriptor,
            root_identity=f"{self.owner_domain}:{descriptor.contract_id}",
            source_event_identity=f"event:{descriptor.contract_id}",
            source_version=descriptor.step,
            terminal_result=True,
            case_no=identity.case_no,
        )
        return HistoricalBaselineOwnerObservationReadback(identity, (observation,))


def _install_fake_adapters(monkeypatch, calls, constructed, *, failure=None):
    class_names = {
        "orders": "MySqlHistoricalBaselineOrdersOwnerAdapter",
        "matching": "MySqlHistoricalBaselineMatchingOwnerAdapter",
        "contract_signing": "MySqlHistoricalBaselineContractSigningOwnerAdapter",
        "client_finance": "MySqlHistoricalBaselineClientFinanceOwnerAdapter",
        "scheduling": "MySqlHistoricalBaselineSchedulingOwnerAdapter",
        "staff_payables": "MySqlHistoricalBaselineStaffPayablesOwnerAdapter",
    }

    for owner_domain, class_name in class_names.items():
        def build(connection, *args, _owner=owner_domain, **kwargs):
            constructed.append((_owner, connection, args, kwargs))
            return _FakeOwnerPort(_owner, connection, calls, failure)

        monkeypatch.setattr(composition, class_name, build)


def test_composition_builds_exact_six_owner_set_on_one_borrowed_connection(monkeypatch):
    connection = _BorrowedConnection()
    calls: list[tuple[str, str, bool]] = []
    constructed: list[tuple[str, object, tuple[object, ...], dict[str, object]]] = []
    clock = object()
    _install_fake_adapters(monkeypatch, calls, constructed)

    query = composition.compose_historical_baseline_owner_vector_v2_query(
        connection, scheduling_clock=clock
    )
    projection = query.query(
        HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE)
    )

    assert tuple(item[0] for item in constructed) == _OWNER_NAMES
    assert all(item[1] is connection for item in constructed)
    assert all(not item[2] for item in constructed)
    assert all(not item[3] for item in constructed if item[0] != "scheduling")
    scheduling = next(item for item in constructed if item[0] == "scheduling")
    assert scheduling[3] == {"clock": clock}
    assert calls == [
        (descriptor.owner_domain, descriptor.contract_id, False)
        for descriptor in _READ_ORDER
    ]
    assert projection.identity == _IDENTITY
    assert projection.catalog_version == 2
    assert connection.transaction_calls == []


def test_composition_propagates_locked_mode_and_is_deterministic(monkeypatch):
    connection = _BorrowedConnection()
    calls: list[tuple[str, str, bool]] = []
    constructed: list[tuple[str, object, tuple[object, ...], dict[str, object]]] = []
    _install_fake_adapters(monkeypatch, calls, constructed)

    query = composition.compose_historical_baseline_owner_vector_v2_query(connection)
    request = HistoricalBaselineOwnerVectorV2QueryRequest(
        _IDENTITY, _PROVENANCE, for_update=True
    )
    first = query.query(request)
    second = query.query(request)

    expected = [
        (descriptor.owner_domain, descriptor.contract_id, True)
        for descriptor in _READ_ORDER
    ]
    assert calls == expected + expected
    assert first == second
    assert connection.transaction_calls == []


@pytest.mark.parametrize("failure", ["missing", "duplicate", "extra", "malformed"])
def test_vector_seam_rejects_non_exact_owner_bindings(failure):
    ports = {
        owner: _FakeOwnerPort(owner, object(), []) for owner in _OWNER_NAMES
    }
    if failure == "missing":
        bindings = {key: value for key, value in ports.items() if key != "orders"}
    elif failure == "duplicate":
        bindings = tuple(ports.items()) + (("orders", ports["orders"]),)
    elif failure == "extra":
        bindings = {**ports, "unknown": ports["orders"]}
    else:
        ports["orders"].owner_domain = "matching"
        bindings = ports

    with pytest.raises(HistoricalBaselineOwnerVectorError):
        HistoricalBaselineOwnerVectorV2Query.from_ports(bindings)


def test_owner_failure_returns_no_partial_projection_or_transaction_effect(monkeypatch):
    connection = _BorrowedConnection()
    calls: list[tuple[str, str, bool]] = []
    constructed: list[tuple[str, object, tuple[object, ...], dict[str, object]]] = []
    failed_descriptor = _READ_ORDER[2]
    _install_fake_adapters(
        monkeypatch,
        calls,
        constructed,
        failure=failed_descriptor.contract_id,
    )
    query = composition.compose_historical_baseline_owner_vector_v2_query(connection)

    with pytest.raises(HistoricalBaselineOwnerVectorError) as error:
        query.query(HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE))

    assert error.value.code == (
        f"historical_baseline_owner_vector_v2_{failed_descriptor.owner_domain}_read_failed"
    )
    assert calls == [
        (descriptor.owner_domain, descriptor.contract_id, False)
        for descriptor in _READ_ORDER[:3]
    ]
    assert connection.transaction_calls == []


def test_composition_propagates_vector_construction_errors_without_fallback(monkeypatch):
    connection = _BorrowedConnection()
    calls: list[tuple[str, str, bool]] = []
    constructed: list[tuple[str, object, tuple[object, ...], dict[str, object]]] = []
    _install_fake_adapters(monkeypatch, calls, constructed)

    def malformed_orders(connection):
        return object()

    monkeypatch.setattr(
        composition, "MySqlHistoricalBaselineOrdersOwnerAdapter", malformed_orders
    )

    with pytest.raises(HistoricalBaselineOwnerVectorError) as error:
        composition.compose_historical_baseline_owner_vector_v2_query(connection)

    assert error.value.code == "historical_baseline_owner_vector_v2_orders_port_invalid"
    assert connection.transaction_calls == []

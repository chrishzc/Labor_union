"""
File: test_historical_baseline_staff_payables_owner_adapter.py
Description: 驗證 Staff Payables HCAT adapter 的完整來源向量、鎖定傳遞與 fail-closed 邊界。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalOperationalBaselineError,
    HistoricalOrderIdentity,
    build_historical_baseline_owner_root_vector_v2,
)
from infrastructure.mysql.historical_baseline_staff_payables_owner_adapter import (
    MySqlHistoricalBaselineStaffPayablesOwnerAdapter,
)


IDENTITY = HistoricalOrderIdentity("order:CASE-1", "CASE-1")
DESCRIPTOR = next(
    item
    for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.owner_domain == "staff_payables"
)


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows):
        self.cursor_instance = Cursor(rows)
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    def cursor(self):
        return self.cursor_instance

    def begin(self):
        self.begin_count += 1

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1


def _rows():
    return [
        {"row_kind": "payroll_account", "case_no": "CASE-1", "version": 7},
        {
            "row_kind": "obligation",
            "case_no": "CASE-1",
            "identity": "obligation:1",
            "staff_id": 8,
            "assignment_id": 3,
            "direction": "payable_to_staff",
            "version": 4,
            "status": "open",
            "amount_due_ntd": 1_000,
            "current_event_id": 11,
            "resulting_version": 4,
            "event_type": "rebuilt",
            "event_amount_ntd": 1_000,
            "projection_amount_ntd": 1_000,
            "net_paid_ntd": 1_000,
            "balance_ntd": 0,
            "projection_status": "completed",
            "account_version": 5,
            "projection_version": 5,
            "target_event_id": 21,
            "target_staff_id": 8,
        },
        {
            "row_kind": "payout",
            "case_no": "CASE-1",
            "identity": "21",
            "related_identity": "obligation:1",
            "staff_id": 8,
            "version": 21,
            "event_type": "payout",
            "event_amount_ntd": 1_000,
            "allocated_amount_ntd": 1_000,
            "allocation_ordinal": 1,
            "reversal_of_event_id": None,
            "target_event_id": None,
            "target_staff_id": None,
            "finance_import_row_id": 31,
            "bank_identity_hash": "a" * 64,
            "reconciliation_reference": "bank-row:31",
            "target_event_type": None,
            "target_event_amount_ntd": None,
            "linked_staff_id": 8,
        },
    ]


def _read(rows=None, *, for_update=False):
    connection = Connection(_rows() if rows is None else rows)
    result = MySqlHistoricalBaselineStaffPayablesOwnerAdapter(
        connection
    ).read_owner_observations(IDENTITY, DESCRIPTOR, for_update=for_update)
    return result, connection


def _compose_with_staff(staff_observations):
    observations = []
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2:
        if descriptor == DESCRIPTOR:
            observations.extend(staff_observations)
            continue
        observations.append(
            HistoricalBaselineOwnerObservation(
                descriptor,
                f"root:{descriptor.contract_id}",
                f"event:{descriptor.contract_id}",
                1,
                True,
                None,
                IDENTITY.case_no,
            )
        )
    return build_historical_baseline_owner_root_vector_v2(
        observations,
        identity=IDENTITY,
    )


def test_returns_every_typed_source_version_without_scalar_collapse():
    result, _connection = _read()

    observations = result.observations
    assert len(observations) == 8
    assert all(item.available and item.terminal_result is True for item in observations)
    assert {item.source_version for item in observations} == {1, 4, 5, 7, 21}
    assert {
        item.root_identity.split(":", 1)[0] for item in observations
    } == {
        "payroll_case_account",
        "staff_obligation",
        "staff_obligation_event",
        "staff_payable_account",
        "staff_payable_projection",
        "staff_payout_event",
        "staff_payout_allocation",
        "staff_bank_fact",
    }
    assert len({item.canonical_order_key for item in observations}) == len(observations)


def test_obligation_and_projection_with_same_raw_identity_compose_as_distinct_events():
    result, _connection = _read()

    vector = _compose_with_staff(result.observations)
    shared_raw_identity = {
        item.root_identity: item.source_event_identity
        for item in vector
        if item.descriptor == DESCRIPTOR
        and item.root_identity.endswith(":obligation:1")
    }

    assert shared_raw_identity == {
        "staff_obligation:obligation:1": "staff_obligation:obligation:1",
        "staff_payable_projection:obligation:1": (
            "staff_payable_projection:obligation:1"
        ),
    }


def test_same_typed_source_identity_with_different_version_still_fails_vector_drift():
    result, _connection = _read()
    source = next(
        item
        for item in result.observations
        if item.root_identity == "staff_obligation:obligation:1"
    )

    with pytest.raises(
        HistoricalOperationalBaselineError,
        match="historical_baseline_v2_source_version_drift",
    ):
        _compose_with_staff(
            result.observations
            + (replace(source, source_version=source.source_version + 1),)
        )


def test_multiple_staff_accounts_keep_each_current_version():
    rows = deepcopy(_rows())
    rows.extend(
        [
            {
                **rows[1],
                "identity": "obligation:2",
                "staff_id": 9,
                "assignment_id": 4,
                "current_event_id": 12,
                "account_version": 9,
                "projection_version": 9,
                "target_event_id": 22,
                "target_staff_id": 9,
            },
            {
                **rows[2],
                "identity": "22",
                "related_identity": "obligation:2",
                "staff_id": 9,
                "version": 22,
                "finance_import_row_id": 32,
                "bank_identity_hash": "b" * 64,
                "reconciliation_reference": "bank-row:32",
                "linked_staff_id": 9,
            },
        ]
    )

    result, _connection = _read(rows)

    account_versions = {
        (item.root_identity, item.source_version)
        for item in result.observations
        if item.root_identity.startswith("staff_payable_account:")
    }
    assert account_versions == {
        ("staff_payable_account:8", 5),
        ("staff_payable_account:9", 9),
    }
    assert all(item.available and item.terminal_result for item in result.observations)


def test_zero_based_recovery_source_version_is_preserved():
    rows = _rows() + [
        {
            "row_kind": "recovery",
            "case_no": "CASE-1",
            "identity": "recovery:1",
            "staff_id": 8,
            "version": 0,
            "status": "open",
            "amount_due_ntd": 300,
            "event_amount_ntd": 300,
            "source_event_ids": "[21]",
            "source_obligation_identities": '["obligation:1"]',
            "source_bank_fact_identities": '["finance-import-row:31"]',
            "recovery_event_id": None,
        }
    ]

    result, _connection = _read(rows)

    recovery = next(
        item
        for item in result.observations
        if item.root_identity == "staff_overpayment_recovery:recovery:1"
    )
    assert recovery.available
    assert recovery.source_version == 0


def test_for_update_is_forwarded_and_connection_lifecycle_remains_borrowed():
    _result, connection = _read(for_update=True)

    assert len(connection.cursor_instance.calls) == 1
    statement, parameters = connection.cursor_instance.calls[0]
    assert statement.rstrip().endswith("FOR UPDATE")
    assert parameters == ("CASE-1",) * 5
    assert (
        connection.begin_count,
        connection.commit_count,
        connection.rollback_count,
        connection.close_count,
    ) == (0, 0, 0, 0)


def test_open_obligation_is_available_but_nonterminal():
    rows = deepcopy(_rows())
    rows[1].update(
        projection_status="partially_paid",
        net_paid_ntd=400,
        balance_ntd=600,
    )
    rows[2].update(event_amount_ntd=400, allocated_amount_ntd=400)

    result, _connection = _read(rows)

    assert result.observations
    assert all(item.available for item in result.observations)
    assert all(item.terminal_result is False for item in result.observations)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows[2].update(case_no="CASE-OTHER"),
        lambda rows: rows[2].update(staff_id=9),
        lambda rows: rows.append(deepcopy(rows[1])),
        lambda rows: rows[1].update(projection_version="5"),
        lambda rows: rows[2].update(allocated_amount_ntd=999),
    ],
)
def test_cross_case_staff_duplicate_malformed_and_incomplete_lineage_fail_closed(mutate):
    rows = deepcopy(_rows())
    mutate(rows)

    result, _connection = _read(rows)

    assert len(result.observations) == 1
    assert not result.observations[0].available
    assert result.observations[0].unavailable_code == (
        "staff_payables_step_11_staff_payout_readback_unavailable"
    )


def test_missing_and_malformed_row_sets_fail_closed():
    missing, _connection = _read([])
    malformed, _connection = _read(["not-a-row"])

    assert not missing.observations[0].available
    assert not malformed.observations[0].available


def test_descriptor_identity_and_lock_mode_are_strict():
    adapter = MySqlHistoricalBaselineStaffPayablesOwnerAdapter(Connection(_rows()))
    orders_descriptor = next(
        item
        for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
        if item.owner_domain == "orders"
    )

    with pytest.raises(ValueError, match="descriptor_unsupported"):
        adapter.read_owner_observations(IDENTITY, orders_descriptor)
    with pytest.raises(TypeError, match="read mode"):
        adapter.read_owner_observations(IDENTITY, DESCRIPTOR, for_update=1)

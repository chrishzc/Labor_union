"""
File: test_historical_baseline_matching_owner_adapter.py
Description: 驗證 Matching HCAT owner adapter 的事件血緣、鎖定與 fail-closed 行為。
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalOrderIdentity,
)
from infrastructure.mysql.historical_baseline_matching_owner_adapter import (
    MySqlHistoricalBaselineMatchingOwnerAdapter,
)


IDENTITY = HistoricalOrderIdentity("order:CASE-1", "CASE-1")
DESCRIPTORS = {
    item.root_identity_kind: item
    for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.owner_domain == "matching"
}


class _Cursor:
    def __init__(self, data):
        self.data = data
        self.calls = []
        self._rows = ()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, params):
        self.calls.append((statement, params))
        sql = statement.lower()
        if "candidate_contact_pools" in sql:
            self._rows = self.data.get("pool", ())
        elif "candidate_contact_entries" in sql:
            self._rows = self.data.get("entries", ())
        elif "candidate_contact_events" in sql:
            self._rows = self.data.get("pool_events", ())
        elif "criteria_snapshots" in sql:
            self._rows = self.data.get("criteria", ())
        elif "matching_coordination_events" in sql:
            self._rows = self.data.get("matching_events", ())
        elif "package_lineage" in sql:
            self._rows = self.data.get("package", ())
        elif "plan_segments" in sql:
            self._rows = self.data.get("segments", ())
        elif "matching_plans" in sql:
            self._rows = self.data.get("plans", ())
        else:
            raise AssertionError(statement)

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, data):
        self.cursor_instance = _Cursor(data)
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1


def _pool_data(*, status="active", events=None):
    return {
        "pool": ({"id": 9, "case_no": "CASE-1"},),
        "entries": ({"id": 10, "pool_id": 9, "staff_id": 7, "status": status, "active_marker": 1},),
        "pool_events": tuple(events or ({"id": 2, "pool_id": 9, "candidate_id": None, "event_type": "candidates_added", "event_key": "added-old", "payload": json.dumps({"candidate_ids": [10]})},)),
    }


def test_candidate_pool_uses_earliest_matching_added_event_and_exact_successor():
    data = _pool_data(
        status="selected",
        events=(
            {"id": 2, "pool_id": 9, "candidate_id": None, "event_type": "candidates_added", "event_key": "added-old", "payload": {"candidate_ids": [10]}},
            {"id": 4, "pool_id": 9, "candidate_id": None, "event_type": "candidates_added", "event_key": "added-new", "payload": {"candidate_ids": [10]}},
            {"id": 5, "pool_id": 9, "candidate_id": 10, "event_type": "candidate_selected", "event_key": "selected-10", "payload": {"candidate_id": 10}},
        ),
    )
    connection = _Connection(data)
    observation = MySqlHistoricalBaselineMatchingOwnerAdapter(connection).read_owner_observations(
        IDENTITY, DESCRIPTORS["candidate_pool"]
    ).observations[0]
    assert observation.available
    assert observation.source_event_identity == "added-old"
    assert observation.source_version == 2
    assert connection.commit_count == connection.rollback_count == connection.close_count == 0


def test_contact_and_willingness_use_latest_exact_candidate_events():
    events = (
        {"id": 2, "pool_id": 9, "candidate_id": None, "event_type": "candidates_added", "event_key": "added", "payload": {"candidate_ids": [10]}},
        {"id": 3, "pool_id": 9, "candidate_id": 10, "event_type": "info_1_sent", "event_key": "info-1-old", "payload": {"delivery_status": "sent"}},
        {"id": 4, "pool_id": 9, "candidate_id": 10, "event_type": "info_1_sent", "event_key": "info-1-new", "payload": {"delivery_status": "manually_confirmed"}},
        {"id": 5, "pool_id": 9, "candidate_id": 10, "event_type": "info_2_sent", "event_key": "info-2", "payload": {"delivery_status": "sent"}},
        {"id": 6, "pool_id": 9, "candidate_id": 10, "event_type": "willingness_changed", "event_key": "willing-old", "payload": {"willingness": "unwilling"}},
        {"id": 7, "pool_id": 9, "candidate_id": 10, "event_type": "willingness_changed", "event_key": "willing-new", "payload": {"willingness": "willing"}},
    )
    connection = _Connection(_pool_data(events=events))
    adapter = MySqlHistoricalBaselineMatchingOwnerAdapter(connection)
    contact = adapter.read_owner_observations(IDENTITY, DESCRIPTORS["candidate_contact"])
    willingness = adapter.read_owner_observations(IDENTITY, DESCRIPTORS["willingness_binding"])
    assert [item.source_event_identity for item in contact.observations] == ["info-1-new", "info-2"]
    assert [item.source_version for item in contact.observations] == [4, 5]
    assert willingness.observations[0].source_event_identity == "willing-new"
    assert willingness.observations[0].terminal_result is True


def _matching_data():
    sources = [{"source_kind": "orders_terms", "source_id": "CASE-1", "version": 4, "fingerprint": "a" * 64}]
    package = {
        "package_id": "package-1",
        "version": 4,
        "criteria_snapshot_id": "criteria-1",
        "source_versions": sources,
        "candidate_results": [{"candidate_id": "candidate-1", "staff_id": 7}],
        "segments": [{"staff_id": 7, "sequence": 1, "service_dates": ["2026-08-01", "2026-08-02"]}],
    }
    return {
        "criteria": ({"id": 11, "snapshot_id": "criteria-1", "case_no": "CASE-1", "criteria_version": 4, "criteria_snapshot": {"criteria": {"days": 2}}, "source_version_tuple": sources},),
        "package": ({"id": 12, "package_id": "package-1", "case_no": "CASE-1", "criteria_snapshot_id": 11, "package_version": 4, "package_state": "accepted", "package_snapshot": package, "source_version_tuple": sources},),
        "matching_events": ({"id": 20, "event_id": "decision-1", "case_no": "CASE-1", "criteria_snapshot_id": 11, "package_lineage_id": 12, "event_type": "customer_decision", "expected_version": 3, "resulting_version": 4, "event_payload": {"result_state": "accepted", "package_id": "package-1", "cross_domain_request": {"candidate_id": "candidate-1"}}, "source_version_tuple": sources},),
    }


@pytest.mark.parametrize("kind", ["selected_staff", "customer_decision"])
def test_selection_requires_complete_canonical_package_criteria_and_decision(kind):
    connection = _Connection(_matching_data())
    observation = MySqlHistoricalBaselineMatchingOwnerAdapter(connection).read_owner_observations(
        IDENTITY, DESCRIPTORS[kind], for_update=True
    ).observations[0]
    assert observation.available
    assert observation.source_version == 4
    assert all("FOR UPDATE" in statement.upper() for statement, _ in connection.cursor_instance.calls)


def test_selection_source_drift_is_unavailable():
    data = _matching_data()
    data["matching_events"] = (dict(data["matching_events"][0], source_version_tuple=[]),)
    observation = MySqlHistoricalBaselineMatchingOwnerAdapter(_Connection(data)).read_owner_observations(
        IDENTITY, DESCRIPTORS["customer_decision"]
    ).observations[0]
    assert not observation.available


def test_caregiver_binding_requires_exact_current_plan_segments_and_package():
    data = _matching_data()
    data.update(
        {
            "plans": ({"id": 50, "case_no": "CASE-1", "version": 2, "status": "accepted", "is_active": 1},),
            "segments": ({"id": 51, "plan_id": 50, "case_no": "CASE-1", "segment_order": 1, "staff_id": 7, "assigned_start_date": date(2026, 8, 1), "assigned_end_date": date(2026, 8, 2)},),
        }
    )
    observation = MySqlHistoricalBaselineMatchingOwnerAdapter(_Connection(data)).read_owner_observations(
        IDENTITY, DESCRIPTORS["caregiver_binding"]
    ).observations[0]
    assert observation.available
    assert observation.source_event_identity == "matching.package:package-1"


def test_unsupported_descriptor_fails_before_any_query():
    connection = _Connection({})
    descriptor = DESCRIPTORS["candidate_pool"]
    tampered = type(descriptor)(
        descriptor.contract_id + ":tampered", descriptor.contract_version, descriptor.step,
        descriptor.owner_domain, descriptor.root_identity_kind, descriptor.root_identity_path,
        descriptor.terminal_predicate_id, descriptor.terminal_predicate_version,
        descriptor.repair_target, descriptor.repair_capability, descriptor.source_event_identity,
        descriptor.source_version, descriptor.collection,
    )
    with pytest.raises(ValueError, match="descriptor_unsupported"):
        MySqlHistoricalBaselineMatchingOwnerAdapter(connection).read_owner_observations(IDENTITY, tampered)
    assert connection.cursor_instance.calls == []


def test_willingness_descriptor_is_single_binding_and_rejects_extra_pool_candidates():
    data = _pool_data()
    data["entries"] = (
        data["entries"][0],
        {"id": 11, "pool_id": 9, "staff_id": 8, "status": "active", "active_marker": 1},
    )
    data["pool_events"] = ({"id": 2, "pool_id": 9, "candidate_id": None, "event_type": "candidates_added", "event_key": "added", "payload": {"candidate_ids": [10, 11]}},)
    result = MySqlHistoricalBaselineMatchingOwnerAdapter(_Connection(data)).read_owner_observations(
        IDENTITY, DESCRIPTORS["willingness_binding"]
    )
    assert result.observations[0].unavailable_code.endswith("cardinality_unavailable")


def test_candidates_added_payload_must_match_exact_pool_membership():
    data = _pool_data(events=({"id": 2, "pool_id": 9, "candidate_id": None, "event_type": "candidates_added", "event_key": "added", "payload": {"candidate_ids": [10, 999]}},))
    result = MySqlHistoricalBaselineMatchingOwnerAdapter(_Connection(data)).read_owner_observations(
        IDENTITY, DESCRIPTORS["candidate_pool"]
    )
    assert not result.observations[0].available


def test_newer_rejected_customer_decision_invalidates_prior_acceptance():
    data = _matching_data()
    accepted = data["matching_events"][0]
    rejected = dict(accepted, id=21, event_id="decision-2", event_payload={"result_state": "rejected", "package_id": "package-1", "cross_domain_request": {"candidate_id": "candidate-1"}})
    data["matching_events"] = (accepted, rejected)
    result = MySqlHistoricalBaselineMatchingOwnerAdapter(_Connection(data)).read_owner_observations(
        IDENTITY, DESCRIPTORS["selected_staff"]
    )
    assert result.observations[0].unavailable_code.endswith("stale")


def test_source_version_tuple_requires_typed_fields():
    data = _matching_data()
    data["matching_events"] = (dict(data["matching_events"][0], source_version_tuple=[{"version": 1}]),)
    result = MySqlHistoricalBaselineMatchingOwnerAdapter(_Connection(data)).read_owner_observations(
        IDENTITY, DESCRIPTORS["customer_decision"]
    )
    assert not result.observations[0].available

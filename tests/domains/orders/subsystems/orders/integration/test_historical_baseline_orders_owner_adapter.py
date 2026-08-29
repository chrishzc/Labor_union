"""
File: test_historical_baseline_orders_owner_adapter.py
Description: 驗證 Orders owner adapter 的精確事件綁定、鎖定與 fail-closed 行為。
"""

from __future__ import annotations

from datetime import date, time

import pytest

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalOrderIdentity,
)
from infrastructure.mysql.historical_baseline_orders_owner_adapter import (
    MySqlHistoricalBaselineOrdersOwnerAdapter,
)


IDENTITY = HistoricalOrderIdentity("order:CASE-1", "CASE-1")
_DESCRIPTORS = {
    item.step: item
    for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.owner_domain == "orders"
}


def _order(**changes):
    row = {
        "case_no": "CASE-1",
        "client_id": 7,
        "client_row_id": 7,
        "client_case_no": "CASE-1",
        "identity_status": "eligible",
        "lifecycle_version": 4,
        "status": "服務中",
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 3),
        "service_days": 3,
        "service_hours_per_day": 8,
        "floor_fee": 0,
        "service_start_time": time(9),
        "service_end_time": time(17),
        "service_end_day_offset": 0,
        "actual_start_date": date(2026, 8, 1),
        "actual_end_date": None,
        "contract_identity": "contract:1",
    }
    row.update(changes)
    return row


def _terms(**changes):
    row = {
        "id": 19,
        "case_no": "CASE-1",
        "expected_order_version": 3,
        "resulting_order_version": 4,
        "receipt_id": 20,
        "receipt_case_no": "CASE-1",
        "receipt_order_version": 4,
        "receipt_lifecycle_event_id": 21,
    }
    row.update(changes)
    return row


def _lifecycle(**changes):
    row = {
        "id": 21,
        "case_no": "CASE-1",
        "trigger_event": "terms_changed",
        "before_status": "訂單成立",
        "after_status": "服務中",
        "expected_version": 3,
    }
    row.update(changes)
    return row


def _actual(**changes):
    row = {
        "id": 31,
        "case_no": "CASE-1",
        "event_type": "confirmed",
        "after_actual_start_date": date(2026, 8, 1),
        "expected_order_version": 3,
        "resulting_order_version": 4,
        "receipt_id": 32,
        "receipt_case_no": "CASE-1",
        "receipt_actual_start_date": date(2026, 8, 1),
        "receipt_order_version": 4,
        "actual_start_event_id": 31,
    }
    row.update(changes)
    return row


def _completion(**changes):
    row = {
        "id": 41,
        "case_no": "CASE-1",
        "trigger_event": "evaluation_time_reached",
        "before_status": "服務中",
        "after_status": "訂單完成",
        "expected_version": 3,
        "resulting_order_version": 4,
        "receipt_id": 42,
        "receipt_case_no": "CASE-1",
        "receipt_lifecycle_event_id": 41,
        "receipt_order_version": 4,
    }
    row.update(changes)
    return row


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
        normalized = statement.lower()
        if "from orders o join clients" in normalized:
            self._rows = self.data.get("order", ())
        elif "from order_actual_start_events" in normalized:
            self._rows = self.data.get("actual", ())
        elif "order_auto_completion_apply_receipts" in normalized:
            self._rows = self.data.get("completion", ())
        elif "from order_terms_change_events" in normalized:
            self._rows = self.data.get("terms", ())
        elif "from historical_order_adoption_receipts" in normalized:
            self._rows = self.data.get("adoption", ())
        elif "from order_lifecycle_state_events" in normalized:
            self._rows = self.data.get("lifecycle", ())
        else:
            raise AssertionError(statement)

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, data):
        self.cursor_instance = _Cursor(data)
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def _adapter(data):
    connection = _Connection(data)
    return MySqlHistoricalBaselineOrdersOwnerAdapter(connection), connection


def test_step_one_binds_order_client_terms_and_terms_lifecycle_event():
    adapter, connection = _adapter({"order": (_order(),), "terms": (_terms(),), "lifecycle": (_lifecycle(),)})

    result = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1])
    observation = result.observations[0]

    assert observation.available
    assert observation.root_identity == "order:CASE-1"
    assert observation.source_event_identity == "orders-terms-event:CASE-1:19"
    assert observation.source_version == 4
    assert observation.terminal_result is True
    assert all("FOR UPDATE" not in statement.upper() for statement, _ in connection.cursor_instance.calls)
    assert connection.commit_count == connection.rollback_count == 0


@pytest.mark.parametrize(
    ("step", "data", "expected_identity"),
    [
        (10, {"order": (_order(),), "actual": (_actual(),)}, "orders-actual-start-event:CASE-1:31"),
        (11, {"order": (_order(status="訂單完成"),), "completion": (_completion(),)}, "orders-completion-event:CASE-1:41"),
    ],
)
def test_step_ten_and_eleven_bind_immutable_event_receipt(step, data, expected_identity):
    adapter, _ = _adapter(data)

    observation = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[step]).observations[0]

    assert observation.available
    assert observation.root_identity == expected_identity
    assert observation.source_event_identity == expected_identity
    assert observation.source_version == 4


def test_locked_reads_append_for_update_to_every_select():
    adapter, connection = _adapter({"order": (_order(),), "terms": (_terms(),), "lifecycle": (_lifecycle(),)})

    adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1], for_update=True)

    assert connection.cursor_instance.calls
    assert all(statement.rstrip().upper().endswith("FOR UPDATE") for statement, _ in connection.cursor_instance.calls)


@pytest.mark.parametrize(
    ("step", "data", "code"),
    [
        (1, {"order": ()}, "orders_step_1_order_missing"),
        (1, {"order": (_order(),), "terms": (_terms(), _terms(id=20)), "lifecycle": (_lifecycle(),)}, "orders_step_1_terms_event_ambiguous"),
        (10, {"order": (_order(),), "actual": (_actual(resulting_order_version=3),)}, "orders_step_10_event_missing"),
        (11, {"order": (_order(status="訂單完成"),), "completion": (_completion(receipt_id=None),)}, "orders_step_11_event_invalid"),
    ],
)
def test_missing_ambiguous_stale_and_receipt_only_facts_are_unavailable(step, data, code):
    adapter, _ = _adapter(data)

    observation = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[step]).observations[0]

    assert observation.available is False
    assert observation.unavailable_code == code


def test_cross_case_and_partial_order_are_unavailable():
    adapter, _ = _adapter({"order": (_order(client_case_no="OTHER"),)})
    cross_case = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1]).observations[0]
    assert cross_case.unavailable_code == "orders_step_1_cross_case"

    adapter, _ = _adapter({"order": (_order(service_days=None),)})
    partial = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1]).observations[0]
    assert partial.unavailable_code == "orders_step_1_terms_incomplete"


def test_historical_adoption_is_accepted_only_when_exact():
    adoption = {
        "id": 55,
        "case_no": "CASE-1",
        "source_event_identity": "historical-orders:row:1",
        "outcome": "adopted",
        "expected_version": 3,
        "resulting_version": 4,
        "lifecycle_event_id": 21,
    }
    adapter, _ = _adapter({"order": (_order(),), "adoption": (adoption,), "lifecycle": (_lifecycle(trigger_event="historical_order_adoption"),)})
    observation = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1]).observations[0]
    assert observation.source_event_identity == "historical-orders:row:1"
    assert observation.source_version == 55

    adapter, _ = _adapter({"order": (_order(),), "adoption": (dict(adoption, lifecycle_event_id=999),), "lifecycle": (_lifecycle(),)})
    rejected = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1]).observations[0]
    assert rejected.unavailable_code == "orders_step_1_adoption_invalid"


def test_legitimate_1008_noop_adoption_is_exact_without_lifecycle_event():
    adoption = {
        "id": 56,
        "case_no": "CASE-1",
        "source_event_identity": "historical-orders:noop:1",
        "outcome": "adopted",
        "expected_version": 4,
        "resulting_version": 4,
        "lifecycle_event_id": None,
    }
    adapter, _ = _adapter({"order": (_order(),), "adoption": (adoption,)})

    observation = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1]).observations[0]

    assert observation.available
    assert observation.source_event_identity == "historical-orders:noop:1"
    assert observation.source_version == 56


def test_adoption_transition_requires_historical_adoption_trigger_and_terms_status_matches():
    adoption = {
        "id": 57,
        "case_no": "CASE-1",
        "source_event_identity": "historical-orders:transition:1",
        "outcome": "adopted",
        "expected_version": 3,
        "resulting_version": 4,
        "lifecycle_event_id": 21,
    }
    adapter, _ = _adapter({
        "order": (_order(),),
        "adoption": (adoption,),
        "lifecycle": (_lifecycle(trigger_event="terms_changed"),),
    })
    rejected = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1]).observations[0]
    assert rejected.unavailable_code == "orders_step_1_adoption_invalid"

    adapter, _ = _adapter({
        "order": (_order(),),
        "terms": (_terms(),),
        "lifecycle": (_lifecycle(after_status="訂單成立"),),
    })
    rejected_terms = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1]).observations[0]
    assert rejected_terms.unavailable_code == "orders_step_1_terms_event_invalid"


def test_adoption_rejects_outbox_intent_as_lifecycle_trigger():
    adoption = {
        "id": 58,
        "case_no": "CASE-1",
        "source_event_identity": "historical-orders:transition:2",
        "outcome": "adopted",
        "expected_version": 3,
        "resulting_version": 4,
        "lifecycle_event_id": 21,
    }
    adapter, _ = _adapter({
        "order": (_order(),),
        "adoption": (adoption,),
        "lifecycle": (_lifecycle(trigger_event="historical_order_adopted"),),
    })

    observation = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[1]).observations[0]

    assert observation.unavailable_code == "orders_step_1_adoption_invalid"


def test_adoption_and_terms_reject_zero_lifecycle_identity():
    adoption = {
        "id": 59,
        "case_no": "CASE-1",
        "source_event_identity": "historical-orders:transition:3",
        "outcome": "adopted",
        "expected_version": 3,
        "resulting_version": 4,
        "lifecycle_event_id": 0,
    }
    zero_lifecycle = _lifecycle(id=0, trigger_event="historical_order_adoption")
    adoption_adapter, _ = _adapter({
        "order": (_order(),),
        "adoption": (adoption,),
        "lifecycle": (zero_lifecycle,),
    })
    terms_adapter, _ = _adapter({
        "order": (_order(),),
        "terms": (_terms(receipt_lifecycle_event_id=0),),
        "lifecycle": (_lifecycle(id=0),),
    })

    adoption_observation = adoption_adapter.read_owner_observations(
        IDENTITY, _DESCRIPTORS[1]
    ).observations[0]
    terms_observation = terms_adapter.read_owner_observations(
        IDENTITY, _DESCRIPTORS[1]
    ).observations[0]

    assert adoption_observation.unavailable_code == "orders_step_1_adoption_invalid"
    assert terms_observation.unavailable_code == "orders_step_1_terms_event_invalid"


@pytest.mark.parametrize("event_type", ["unknown", None])
def test_actual_start_requires_released_event_type(event_type):
    adapter, _ = _adapter({"order": (_order(),), "actual": (_actual(event_type=event_type),)})

    observation = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[10]).observations[0]

    assert observation.unavailable_code == "orders_step_10_event_invalid"


def test_completion_requires_service_transition_and_positive_current_version():
    adapter, _ = _adapter({
        "order": (_order(status="訂單完成", lifecycle_version=0),),
        "completion": (_completion(expected_version=-1, resulting_order_version=0),),
    })
    unavailable = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[11]).observations[0]
    assert unavailable.unavailable_code == "orders_step_11_current_root_incomplete"

    adapter, _ = _adapter({
        "order": (_order(status="訂單完成"),),
        "completion": (_completion(before_status="訂單成立"),),
    })
    unavailable = adapter.read_owner_observations(IDENTITY, _DESCRIPTORS[11]).observations[0]
    assert unavailable.unavailable_code == "orders_step_11_event_invalid"


def test_unsupported_descriptor_fails_closed_without_query():
    adapter, connection = _adapter({})
    descriptor = _DESCRIPTORS[1]
    with pytest.raises(ValueError, match="descriptor_unsupported"):
        adapter.read_owner_observations(
            IDENTITY,
            type(descriptor)(
                descriptor.contract_id + ":tampered",
                descriptor.contract_version,
                descriptor.step,
                descriptor.owner_domain,
                descriptor.root_identity_kind,
                descriptor.root_identity_path,
                descriptor.terminal_predicate_id,
                descriptor.terminal_predicate_version,
                descriptor.repair_target,
                descriptor.repair_capability,
                descriptor.source_event_identity,
                descriptor.source_version,
                descriptor.collection,
            ),
        )
    assert connection.cursor_instance.calls == []

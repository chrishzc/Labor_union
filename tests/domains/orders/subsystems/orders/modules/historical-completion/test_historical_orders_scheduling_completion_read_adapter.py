"""Historical count roots consumed by the Orders completion read adapter."""

from datetime import date

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.historical_orders_scheduling_completion_read_adapter import (
    _CURRENT_CASE_READ_SQL,
    _build_readback,
)


def test_historical_completed_readback_uses_count_roots_without_scheduling_dates() -> None:
    order = {
        "case_no": "CASE-H",
        "lifecycle_version": 3,
        "status": OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value,
        "actual_start_date": date(2026, 8, 1),
        "service_days": 25,
        "service_start_time": None,
        "service_end_time": None,
        "service_end_day_offset": None,
    }
    completion = ({
        "completion_event_id": 31,
        "completion_case_no": "CASE-H",
        "completion_after_status": OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value,
        "completion_expected_version": 2,
    },)
    historical_days = ({
        "historical_event_id": 41,
        "historical_event_identity": "historical-service-days:fingerprint",
        "historical_event_case_no": "CASE-H",
        "historical_event_resulting_day_revision": 1,
        "historical_event_total_actual_service_days": 3,
        "historical_projection_event_id": 41,
        "historical_projection_case_no": "CASE-H",
        "historical_projection_day_revision": 1,
        "historical_projection_total_actual_service_days": 3,
        "historical_item_assignment_id": 7,
        "historical_item_staff_id": 9,
        "historical_item_actual_service_days": 3,
    },)

    result = _build_readback(
        "CASE-H", order, completion, (), (), (), (), historical_days
    )

    assert result.canonical_status is OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED
    assert result.completion_lineage_identity == "orders-completion-event:CASE-H:31"
    assert result.historical_service_day_count_identity == "historical-service-days:fingerprint"
    assert result.historical_assignment_day_counts == (("assignment:7", 9, 3),)
    assert result.official_service_dates == ()
    assert result.official_service_fact_identity is None
    assert result.integrity_blockers == ()


def test_single_snapshot_query_includes_historical_count_roots() -> None:
    assert "historical_service_day_projections" in _CURRENT_CASE_READ_SQL
    assert "historical_service_day_events" in _CURRENT_CASE_READ_SQL
    assert "historical_service_day_items" in _CURRENT_CASE_READ_SQL
    assert OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value in _CURRENT_CASE_READ_SQL

from infrastructure.mysql.historical_orders_stage_projection_repository import (
    _HISTORICAL_PAGE_SQL,
)
from infrastructure.mysql.orders_stage_projection_repository import _PAGE_SQL


def test_historical_scope_extends_existing_stage_query_without_replacing_owner_joins() -> None:
    assert _HISTORICAL_PAGE_SQL != _PAGE_SQL
    assert "historical_order_adoption_receipts" in _HISTORICAL_PAGE_SQL
    assert "completion_fact.receipt_id IS NULL" in _HISTORICAL_PAGE_SQL
    assert "client_fact.client_open_count" in _HISTORICAL_PAGE_SQL
    assert "staff_fact.staff_open_count" in _HISTORICAL_PAGE_SQL
    assert "FROM caregiver_matching_plans" not in _HISTORICAL_PAGE_SQL
    assert "LEFT JOIN caregiver_matching_plans" in _HISTORICAL_PAGE_SQL

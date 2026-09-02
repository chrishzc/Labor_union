"""Repository scope tests for historical-aware Orders stage projection."""

from domains.orders.lifecycle import OrderLifecycleScope
from infrastructure.mysql.historical_orders_stage_projection_repository import (
    _HISTORICAL_PAGE_SQL,
    MySqlHistoricalAwareOrdersStageProjectionRepository,
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


class _Cursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[object, ...] = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self):
        return []


class _Connection:
    def __init__(self) -> None:
        self.last_cursor = _Cursor()

    def cursor(self):
        return self.last_cursor


def test_unfinished_scope_keeps_cancelled_orders_for_terminal_classification() -> None:
    connection = _Connection()

    rows = MySqlHistoricalAwareOrdersStageProjectionRepository(connection).fetch_page(
        after_case_no=None,
        page_size=50,
        lifecycle_scope=OrderLifecycleScope.UNFINISHED,
    )

    assert rows == ()
    assert connection.last_cursor.params == (
        "",
        "unfinished",
        "訂單完成",
        "訂單完成",
        51,
    )
    assert "historical_cancel" not in connection.last_cursor.sql
    assert "o.status = %s" in connection.last_cursor.sql
    assert "historical_done.outcome = 'adopted'" in connection.last_cursor.sql

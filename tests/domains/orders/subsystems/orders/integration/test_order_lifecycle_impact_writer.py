"""
File: test_order_lifecycle_impact_writer.py
Description: 驗證未完成服務可保留空 actual end 的 lifecycle event payload。
"""

from datetime import date
from types import SimpleNamespace

from infrastructure.mysql.order_lifecycle_impact_writer import _lifecycle_payload
from infrastructure.mysql.order_lifecycle_impact_writer import (
    persist_order_lifecycle_projection,
)


def test_lifecycle_payload_preserves_unknown_actual_end_date():
    command = SimpleNamespace(
        candidate=SimpleNamespace(
            actual_end_date=None,
            after_status=SimpleNamespace(value="服務中"),
            alert_codes=("official_service_period_missing",),
            before_status=SimpleNamespace(value="服務中"),
            completion_instant=None,
            business_date=date(2026, 8, 24),
            service_completion_reached=False,
            service_data_lock_should_exist=False,
        ),
        correlation_id=SimpleNamespace(value="test-correlation"),
        reason="complete uniquely paired cooking requirement",
        resulting_order_version=2,
    )

    payload = _lifecycle_payload(command)

    assert payload["actual_end_date"] is None
    assert payload["completion_instant"] is None
    assert payload["service_completion_reached"] is False


def test_lifecycle_projection_owns_order_update_for_typed_command():
    class _Cursor:
        rowcount = 1

        def __init__(self):
            self.statement = None
            self.parameters = None

        def execute(self, statement, parameters):
            self.statement = statement
            self.parameters = parameters

    command = SimpleNamespace(
        candidate=SimpleNamespace(
            case_no="CASE-001",
            actual_end_date=date(2026, 8, 24),
            after_status=SimpleNamespace(value="服務完成"),
        ),
        expected_order_version=4,
        resulting_order_version=5,
    )
    cursor = _Cursor()

    persist_order_lifecycle_projection(cursor, command)

    assert cursor.statement.startswith("UPDATE orders SET")
    assert cursor.parameters == ("服務完成", date(2026, 8, 24), 5, "CASE-001", 4)

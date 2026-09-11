"""Owner-backed case-option coverage for the Assignment Plan mobile tool."""

from infrastructure.mysql.segmented_availability_repository import (
    MySqlSegmentedAvailabilityFactsRepository,
)


class _Cursor:
    def __init__(self):
        self.statement = ""
        self.params = None
        self.closed = False

    def execute(self, sql, params=None):
        self.statement = " ".join(sql.split())
        self.params = tuple(params or ())

    def fetchall(self):
        return [
            {"case_no": "CASE-001", "order_status": "洽談中"},
            {"case_no": "CASE-002", "order_status": "訂單成立"},
            {"case_no": "CASE-003", "order_status": "訂單成立"},
        ]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_assignment_plan_options_require_supported_status_and_confirmed_dates():
    connection = _Connection()
    repository = MySqlSegmentedAvailabilityFactsRepository(lambda: connection)

    items, next_cursor = repository.list_assignment_plan_case_options("CASE-000", 2)

    assert items == (
        {"case_no": "CASE-001", "order_status": "洽談中"},
        {"case_no": "CASE-002", "order_status": "訂單成立"},
    )
    assert next_cursor == "CASE-002"
    assert "o.status IN ('洽談中','訂單成立')" in connection.cursor_instance.statement
    assert "confirmed_service_date_versions" in connection.cursor_instance.statement
    assert "v.is_current=1" in connection.cursor_instance.statement
    assert connection.cursor_instance.params == ("CASE-000", 3)
    assert connection.cursor_instance.closed is True
    assert connection.closed is True

from datetime import date

from infrastructure.mysql.order_detail_query_repository import (
    MySqlOrderDetailQueryRepository,
)


class _Cursor:
    def __init__(self) -> None:
        self.statement = None
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        return False

    def execute(self, statement, parameters):
        self.statement = statement
        self.parameters = parameters

    def fetchone(self):
        return {"case_no": "CASE-1", "start_date": date(2026, 1, 5)}


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()

    def cursor(self):
        return self.cursor_instance


def test_repository_selects_declared_fields_for_only_one_case() -> None:
    connection = _Connection()

    row = MySqlOrderDetailQueryRepository(connection).fetch_by_case_no("CASE-1")

    assert row == {"case_no": "CASE-1", "start_date": date(2026, 1, 5)}
    assert connection.cursor_instance.parameters == ("CASE-1",)
    assert "SELECT *" not in connection.cursor_instance.statement
    assert "binding.group_id AS line_group_id" in connection.cursor_instance.statement
    assert "LEFT JOIN line_order_group_bindings binding ON binding.case_no = o.case_no" in (
        connection.cursor_instance.statement
    )
    assert "o.line_group_id" not in connection.cursor_instance.statement
    assert "WHERE o.case_no = %s" in connection.cursor_instance.statement

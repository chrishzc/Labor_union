"""
File: test_anomaly_necessity_producer_cutover.py
Description: 驗證退役的 SCHEDULE-005 偏好規則不再由 runtime reminder scan 投影。
"""

from datetime import date

from infrastructure.mysql.process_reminder_anomaly_source import _scan_all


class _EmptyCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _parameters=None) -> None:
        self.statements.append(statement)

    def fetchall(self):
        return []


class _EmptyConnection:
    def __init__(self) -> None:
        self.cursor_instance = _EmptyCursor()

    def cursor(self):
        return self.cursor_instance


def test_runtime_scan_does_not_query_or_project_schedule_preference_anomaly() -> None:
    connection = _EmptyConnection()

    assert _scan_all(connection, date(2026, 8, 27)) == ()
    assert all(
        "staff_holiday_availability" not in statement
        for statement in connection.cursor_instance.statements
    )

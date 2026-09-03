"""Regression coverage for the display-only historical assignment overlay."""

from subsystems.scheduling import staff_monthly_calendar_query


class _Cursor:
    def __init__(self):
        self.responses = [{"id": 7}, [], [], [], [], []]
        self.current = None
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        self.current = self.responses.pop(0)

    def fetchone(self):
        return self.current[0] if isinstance(self.current, list) and self.current else self.current

    def fetchall(self):
        return self.current


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        return None


def test_precision_restart_suppresses_the_stale_historical_interval(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(staff_monthly_calendar_query, "get_connection", lambda: connection)

    result = staff_monthly_calendar_query.get_staff_monthly_calendar_schedule(
        staff_id=7,
        year=2026,
        month=7,
    )

    assert all(day["status"] != "historical_assignment" for day in result["days"])
    historical_query, _params = connection.cursor_instance.executed[2]
    assert "orders_historical_precision_restart" in historical_query

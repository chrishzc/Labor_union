from datetime import date

import pytest

from services import multi_caregiver_schedule_read as service


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def assignment(**overrides):
    return {
        "id": 21,
        "case_no": "115000001",
        "staff_id": 8,
        "staff_name": "王月嫂",
        "status": "active",
        "assigned_start_date": date(2026, 6, 1),
        "assigned_end_date": date(2026, 6, 3),
        "actual_hours": 18,
        "service_hours_per_day": 9,
        **overrides,
    }


def test_lists_only_formal_assignments_for_explicit_case(monkeypatch):
    connection = FakeConnection([assignment(), assignment(id=22, staff_id=9)])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.list_case_schedule_assignments(" 115000001 ")

    assert [item["id"] for item in result["assignments"]] == [21, 22]
    sql, params = connection.cursor_obj.executed[0]
    assert params == ("115000001",)
    assert "a.status <> 'cancelled'" in sql
    assert "ORDER BY a.assigned_start_date ASC, a.id ASC" in sql
    assert "staff_schedule" not in sql
    assert connection.closed is True


@pytest.mark.parametrize("case_no", [None, "", "   ", 115000001])
def test_rejects_invalid_case_no_before_opening_connection(monkeypatch, case_no):
    monkeypatch.setattr(service, "get_connection", lambda: pytest.fail("must not connect"))

    with pytest.raises(ValueError, match="non-empty string"):
        service.list_case_schedule_assignments(case_no)


def test_returns_empty_list_when_selected_case_has_no_active_assignments(monkeypatch):
    connection = FakeConnection([])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    assert service.list_case_schedule_assignments("115000001") == {"assignments": []}
    assert connection.closed is True

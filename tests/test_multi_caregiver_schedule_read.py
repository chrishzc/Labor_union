from datetime import date

import pytest

from services import multi_caregiver_schedule_read as service


class FakeCursor:
    def __init__(self, responses):
        self.responses = list(responses)
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
        return self.current

    def fetchall(self):
        return self.current


class FakeConnection:
    def __init__(self, responses):
        self.cursor_obj = FakeCursor(responses)
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
        "client_name": "陳客戶",
        "status": "active",
        "assigned_start_date": date(2026, 6, 1),
        "assigned_end_date": date(2026, 6, 3),
        "planned_hours": None,
        "actual_hours": 18,
        "service_hours_per_day": 9,
        **overrides,
    }


def schedule_day(**overrides):
    return {
        "id": 7,
        "case_no": "115000001",
        "staff_id": 8,
        "assignment_id": 21,
        "work_date": date(2026, 6, 1),
        "is_work_day": True,
        "is_double_pay": False,
        "notes": None,
        **overrides,
    }


def test_reads_explicit_assignment_and_owned_schedule_days(monkeypatch):
    connection = FakeConnection([
        assignment(),
        [schedule_day(), schedule_day(id=8, work_date=date(2026, 6, 2))],
    ])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.get_assignment_schedule(21)

    assert result["assignment"]["staff_name"] == "王月嫂"
    assert [row["work_date"] for row in result["schedule_days"]] == [
        date(2026, 6, 1),
        date(2026, 6, 2),
    ]
    assert connection.cursor_obj.executed[0][1] == (21,)
    assert connection.cursor_obj.executed[1][1] == (21,)
    assert "WHERE assignment_id = %s" in connection.cursor_obj.executed[1][0]
    assert connection.closed is True


@pytest.mark.parametrize("assignment_id", [0, "21", True])
def test_rejects_invalid_assignment_id_before_opening_connection(monkeypatch, assignment_id):
    monkeypatch.setattr(service, "get_connection", lambda: pytest.fail("must not connect"))

    with pytest.raises(ValueError, match="positive integer"):
        service.get_assignment_schedule(assignment_id)


def test_rejects_missing_assignment(monkeypatch):
    connection = FakeConnection([None])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match="does not exist"):
        service.get_assignment_schedule(21)

    assert len(connection.cursor_obj.executed) == 1
    assert connection.closed is True


@pytest.mark.parametrize("invalid_assignment_id", [None, 33])
def test_rejects_schedule_rows_not_owned_by_requested_assignment(monkeypatch, invalid_assignment_id):
    connection = FakeConnection([
        assignment(),
        [schedule_day(assignment_id=invalid_assignment_id)],
    ])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match="does not belong"):
        service.get_assignment_schedule(21)

    assert connection.closed is True

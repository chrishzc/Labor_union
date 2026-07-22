from datetime import date
from decimal import Decimal

import pytest

from services import multi_caregiver_schedule_adjustment_service as subject


class Cursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.statements = []
        self._current = None

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        self._current = self.responses.pop(0) if self.responses else None

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current or []


class Connection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return _CursorContext(self.cursor_instance)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, *args):
        return False


def _assignment(**overrides):
    return {
        "id": 11,
        "case_no": "CASE-1",
        "staff_id": 7,
        "assigned_start_date": date(2026, 7, 1),
        "assigned_end_date": date(2026, 7, 3),
        "status": "active",
        "service_hours_per_day": Decimal("9"),
    } | overrides


def _schedule(**overrides):
    return {
        "id": 21,
        "case_no": "CASE-1",
        "staff_id": 7,
        "assignment_id": 11,
        "work_date": date(2026, 7, 2),
        "is_work_day": True,
        "is_double_pay": False,
        "notes": None,
    } | overrides


def _run(monkeypatch, responses, **request):
    cursor = Cursor(responses)
    connection = Connection(cursor)
    monkeypatch.setattr(subject, "get_connection", lambda: connection)
    result = subject.adjust_assignment_schedule_day(
        11, "2026-07-02", False, True, "請假調整", **request
    )
    return result, connection, cursor


def test_adjusts_only_target_assignment_and_recalculates_hours(monkeypatch):
    result, connection, cursor = _run(
        monkeypatch,
        [
            _assignment(), None, None, _schedule(), None,
            [{"id": 20, "is_work_day": True}, {"id": 21, "is_work_day": False}, {"id": 22, "is_work_day": True}],
            None,
        ],
    )

    assert result["actual_hours"] == Decimal("18")
    assert result["adjusted_schedule_day"]["assignment_id"] == 11
    assert result["adjusted_schedule_day"]["is_work_day"] is False
    assert connection.commits == 1
    assert connection.rollbacks == 0
    update_sql, update_params = cursor.statements[4]
    assert "UPDATE staff_schedule" in update_sql
    assert update_params == (False, True, "請假調整", 21, 11)
    hours_sql, hours_params = cursor.statements[6]
    assert hours_sql.startswith("UPDATE case_staff_assignments SET actual_hours")
    assert hours_params == (Decimal("18"), 11)
    all_sql = "\n".join(sql for sql, _ in cursor.statements).upper()
    assert "INSERT" not in all_sql
    assert "DELETE" not in all_sql
    assert "ON DUPLICATE" not in all_sql
    assert "UPDATE ORDERS" not in all_sql
    assert all("FOR UPDATE" in sql for sql, _ in cursor.statements[:4])


@pytest.mark.parametrize(
    ("assignment", "schedule", "message"),
    [
        (_assignment(status="cancelled"), None, "cancelled assignment"),
        (_assignment(assigned_start_date=None), None, "date range is incomplete"),
        (_assignment(), _schedule(assignment_id=None), "requires review"),
        (_assignment(), _schedule(assignment_id=99), "another assignment"),
        (_assignment(), _schedule(case_no="CASE-OTHER"), "case does not match"),
    ],
)
def test_rejects_cancelled_incomplete_or_unowned_schedule(monkeypatch, assignment, schedule, message):
    responses = [assignment]
    if assignment["status"] != "cancelled" and assignment["assigned_start_date"] is not None:
        responses.extend([None, None, schedule])
    cursor = Cursor(responses)
    connection = Connection(cursor)
    monkeypatch.setattr(subject, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match=message):
        subject.adjust_assignment_schedule_day(11, "2026-07-02", False, False, None)

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert not any("UPDATE staff_schedule" in sql for sql, _ in cursor.statements)


def test_rejects_date_outside_assignment_or_missing_schedule(monkeypatch):
    cursor = Cursor([_assignment()])
    connection = Connection(cursor)
    monkeypatch.setattr(subject, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match="outside"):
        subject.adjust_assignment_schedule_day(11, "2026-07-04", False, False, None)
    assert connection.rollbacks == 1

    cursor = Cursor([_assignment(), None, None, None])
    connection = Connection(cursor)
    monkeypatch.setattr(subject, "get_connection", lambda: connection)
    with pytest.raises(ValueError, match="does not exist"):
        subject.adjust_assignment_schedule_day(11, "2026-07-02", False, False, None)
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    ("payment", "settlement", "message"),
    [({"id": 1}, None, "active staff payment"), (None, {"id": 2}, "active monthly settlement")],
)
def test_rejects_payment_or_settlement_snapshot(monkeypatch, payment, settlement, message):
    cursor = Cursor([_assignment(), payment, settlement])
    connection = Connection(cursor)
    monkeypatch.setattr(subject, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match=message):
        subject.adjust_assignment_schedule_day(11, "2026-07-02", False, False, None)

    assert connection.rollbacks == 1
    assert not any("UPDATE staff_schedule" in sql for sql, _ in cursor.statements)


def test_validates_request_without_opening_a_connection(monkeypatch):
    monkeypatch.setattr(subject, "get_connection", lambda: pytest.fail("connection should not be opened"))

    with pytest.raises(ValueError, match="positive integer"):
        subject.adjust_assignment_schedule_day(True, "2026-07-02", False, False, None)
    with pytest.raises(ValueError, match="boolean"):
        subject.adjust_assignment_schedule_day(11, "2026-07-02", 0, False, None)
    with pytest.raises(ValueError, match="ISO date"):
        subject.adjust_assignment_schedule_day(11, "not-a-date", False, False, None)

from datetime import date, timedelta

from subsystems.scheduling import staff_monthly_calendar_query as staff_monthly_calendar_schedule_service
import pytest


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
        if isinstance(self.current, list):
            return self.current[0] if self.current else None
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


def row(**overrides):
    return {
        "work_date": date(2026, 7, 3),
        "is_work_day": True,
        "is_double_pay": False,
        "notes": None,
        "schedule_id": 100,
        "case_no": "115000001",
        "assignment_id": 1,
        "client_name": "客戶甲",
        **overrides,
    }


def test_get_staff_monthly_calendar_schedule_keeps_per_day_rows_and_base_shape(monkeypatch):
    rows = [
        row(id=10, work_date=date(2026, 7, 3), assignment_id=11, is_work_day=True, client_name="客戶 A"),
        row(id=11, work_date=date(2026, 7, 3), assignment_id=12, is_work_day=False, client_name="客戶 A"),
        row(id=12, work_date=date(2026, 7, 5), assignment_id=13, is_work_day=True, client_name="客戶 B"),
    ]
    lock_rows = [
        {
            "work_date": date(2026, 7, 4),
            "staff_id": 7,
            "lock_id": 90,
            "plan_id": 80,
            "case_no": "115000002",
            "client_name": "客戶 C",
            "order_status": "洽談中",
            "staff_name": "月嫂甲",
        }
    ]
    assignment_buffer_rows = []
    connection = FakeConnection([{"id": 7}, rows, lock_rows, assignment_buffer_rows])
    monkeypatch.setattr(staff_monthly_calendar_schedule_service, "get_connection", lambda: connection)

    result = staff_monthly_calendar_schedule_service.get_staff_monthly_calendar_schedule(
        staff_id=7, year=2026, month=7
    )

    assert result["staff_id"] == 7
    assert result["year"] == 2026
    assert result["month"] == 7
    assert len(result["days"]) == 32
    assert result["days"][0]["status"] == "available"
    assert result["days"][0]["assignment_id"] is None
    assert result["days"][2]["work_date"] == "2026-07-03"
    assert result["days"][2]["status"] == "working"
    assert result["days"][2]["assignment_id"] == 11
    assert result["days"][2]["case_no"] == "115000001"
    assert result["days"][2]["client_name"] == "客戶 A"
    assert result["days"][3]["assignment_id"] == 12
    assert result["days"][3]["status"] == "resting"
    assert result["days"][5]["assignment_id"] == 13
    assert result["days"][5]["status"] == "working"
    waiting = next(
        item
        for item in result["days"]
        if item["work_date"] == "2026-07-04"
        and item["status"] == "waiting_deposit_lock"
    )
    assert waiting["assignment_id"] is None
    assert waiting["case_no"] == "115000002"
    assert waiting["lock_id"] == 90

    assert result["schedule_map"][3]["status"] == "red"
    assert result["schedule_map"][3]["assignment_id"] == 11
    assert result["schedule_map"][5]["status"] == "red"
    assert result["schedule_map"][4]["status"] == "yellow"

    for item in result["days"]:
        assert item["staff_id"] == 7
        assert "work_date" in item
        assert "status" in item
        assert "assignment_id" in item
        assert "case_no" in item
        assert "client_name" in item
        if item["assignment_id"] is not None:
            assert item["assignment_id"] != "115000001"

    query, params = connection.cursor_obj.executed[0]
    assert query == "SELECT 1 AS staff_exists FROM staff WHERE id = %s"
    assert params == (7,)

    query, params = connection.cursor_obj.executed[1]
    assert "JOIN case_staff_assignments" in query
    assert "o.status AS order_status" in query
    assert "o.order_status" not in query
    assert params == (7, date(2026, 7, 1), date(2026, 7, 31))
    query, params = connection.cursor_obj.executed[2]
    assert "JOIN caregiver_availability_locks" in query
    assert "o.status AS order_status" in query
    assert "o.order_status" not in query
    assert params == (7, date(2026, 7, 1), date(2026, 7, 31))
    query, params = connection.cursor_obj.executed[3]
    assert "COALESCE(o.actual_end_date, csa.assigned_end_date) AS calc_end_date" in query
    assert "assignment_id" in query
    assert params == (7,)
    assert connection.closed is True


def test_get_staff_monthly_calendar_schedule_supports_30_day_month(monkeypatch):
    connection = FakeConnection([{"id": 7}, [], [], []])
    monkeypatch.setattr(staff_monthly_calendar_schedule_service, "get_connection", lambda: connection)

    result = staff_monthly_calendar_schedule_service.get_staff_monthly_calendar_schedule(
        staff_id=7, year=2026, month=6
    )

    assert len(result["days"]) == 30
    assert result["days"][0]["status"] == "available"


def test_get_staff_monthly_calendar_schedule_staff_not_found(monkeypatch):
    connection = FakeConnection([None])
    monkeypatch.setattr(staff_monthly_calendar_schedule_service, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match="服務人員不存在"):
        staff_monthly_calendar_schedule_service.get_staff_monthly_calendar_schedule(
            staff_id=999,
            year=2026,
            month=7,
        )


def test_get_staff_monthly_calendar_schedule_supports_31_day_month(monkeypatch):
    connection = FakeConnection([{"id": 7}, [], [], []])
    monkeypatch.setattr(staff_monthly_calendar_schedule_service, "get_connection", lambda: connection)

    result = staff_monthly_calendar_schedule_service.get_staff_monthly_calendar_schedule(
        staff_id=7, year=2026, month=5
    )

    assert len(result["days"]) == 31
    assert result["days"][0]["status"] == "available"
    assert result["days"][-1]["status"] == "available"


def test_get_staff_monthly_calendar_schedule_applies_7_day_buffer_when_end_near_next_month(monkeypatch):
    buffer_rows = [
        {
            "assignment_id": 55,
            "case_no": "115000200",
            "staff_id": 7,
            "calc_end_date": date(2026, 6, 30),
            "client_name": "客戶 Buffer",
            "order_status": "訂單完成",
            "staff_name": "月嫂甲",
        }
    ]
    connection = FakeConnection([{"id": 7}, [], [], buffer_rows])
    monkeypatch.setattr(staff_monthly_calendar_schedule_service, "get_connection", lambda: connection)

    result = staff_monthly_calendar_schedule_service.get_staff_monthly_calendar_schedule(
        staff_id=7, year=2026, month=7
    )

    for day in range(1, 8):
        item = result["days"][day - 1]
        assert item["status"] == "waiting_deposit_lock"
        assert item["assignment_id"] == 55
        assert item["case_no"] == "115000200"
        assert item["staff_id"] == 7
        assert item["lock_id"] is None


def test_get_staff_monthly_calendar_schedule_schedule_only_has_lock_rows(monkeypatch):
    lock_rows = [
        {
            "work_date": date(2026, 7, 10),
            "staff_id": 7,
            "lock_id": 91,
            "plan_id": 81,
            "case_no": "115000003",
            "client_name": "客戶 D",
            "order_status": "洽談中",
            "staff_name": "月嫂甲",
        }
    ]
    connection = FakeConnection([{"id": 7}, [], lock_rows, []])
    monkeypatch.setattr(staff_monthly_calendar_schedule_service, "get_connection", lambda: connection)

    result = staff_monthly_calendar_schedule_service.get_staff_monthly_calendar_schedule(
        staff_id=7, year=2026, month=7
    )

    waiting = result["days"][9]
    assert waiting["status"] == "waiting_deposit_lock"
    assert waiting["assignment_id"] is None
    assert waiting["case_no"] == "115000003"
    assert waiting["lock_id"] == 91
    assert waiting["plan_id"] == 81
    assert result["schedule_map"][10]["status"] == "yellow"


def test_get_staff_monthly_calendar_schedule_cross_month_and_mix(monkeypatch):
    rows = [
        row(id=15, work_date=date(2026, 7, 31), assignment_id=20, is_work_day=True, client_name="客戶 E"),
    ]
    lock_rows = [
        {
            "work_date": date(2026, 7, 1),
            "staff_id": 7,
            "lock_id": 95,
            "plan_id": 85,
            "case_no": "115000004",
            "client_name": "客戶 F",
            "order_status": "洽談中",
            "staff_name": "月嫂甲",
        },
        {
            "work_date": date(2026, 7, 31),
            "staff_id": 7,
            "lock_id": 96,
            "plan_id": 86,
            "case_no": "115000005",
            "client_name": "客戶 G",
            "order_status": "洽談中",
            "staff_name": "月嫂甲",
        }
    ]
    buffer_rows = [
        {
            "assignment_id": 60,
            "case_no": "115000201",
            "staff_id": 7,
            "calc_end_date": date(2026, 6, 28),
            "client_name": "客戶 Buffer 2",
            "order_status": "訂單完成",
            "staff_name": "月嫂甲",
        }
    ]
    connection = FakeConnection([{"id": 7}, rows, lock_rows, buffer_rows])
    monkeypatch.setattr(staff_monthly_calendar_schedule_service, "get_connection", lambda: connection)

    result = staff_monthly_calendar_schedule_service.get_staff_monthly_calendar_schedule(
        staff_id=7, year=2026, month=7
    )

    day_1_items = [d for d in result["days"] if d["work_date"] == "2026-07-01"]
    assert any(d["status"] == "waiting_deposit_lock" and d["lock_id"] == 95 for d in day_1_items)

    for day_idx in range(1, 6):
        date_str = f"2026-07-0{day_idx}"
        items = [d for d in result["days"] if d["work_date"] == date_str]
        assert any(d["status"] == "waiting_deposit_lock" and d["assignment_id"] == 60 for d in items)
        
    day_31_items = [d for d in result["days"] if d["work_date"] == "2026-07-31"]
    assert any(d["status"] == "working" and d["assignment_id"] == 20 for d in day_31_items)
    assert result["schedule_map"][31]["status"] == "red"

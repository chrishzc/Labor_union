from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routes import contracts


CASE_FACTS = {
    "case_no": "115000001",
    "status": "服務中",
    "contract_id": "C-1",
    "service_days": 20,
    "service_hours_per_day": 9,
    "client_identity_status": "一般市民",
    "floor_fee": 500,
    "start_date": "2026-06-01",
    "end_date": "2026-06-20",
    "actual_start_date": None,
    "actual_end_date": None,
    "client_id": 4,
    "client_name": "王小明",
    "client_phone": "0912",
    "client_city": "台北市",
    "client_address": "中正區",
    "service_type": "週休一日",
    "service_time": "09:00",
    "baby_info": "單胞胎",
    "client_notes": "",
    "beclass_query_no": "115000001",
    "survey_details": {"飲食": "素食"},
    "beclass_admin_notes": "",
}


def assignment(assignment_id: int, status: str = "active") -> dict:
    return {
        "assignment_id": assignment_id,
        "case_no": "115000001",
        "staff_id": assignment_id + 10,
        "assignment_sequence": assignment_id,
        "assigned_start_date": "2026-06-01",
        "assigned_end_date": "2026-06-20",
        "planned_hours": 180,
        "actual_hours": None,
        "hourly_rate": 350,
        "floor_fee_allocated": 500,
        "status": status,
        "replacement_reason": None,
        "staff_name": f"月嫂{assignment_id}",
        "staff_identity_card": "A123456789",
        "staff_phone": "0988",
        "staff_email": "staff@example.com",
        "staff_city": "台北市",
        "staff_address": "大安區",
        "weekly_rest_days": "[]",
        "service_regions": "[]",
    }


class FakeCursor:
    def __init__(self, case_facts, assignments):
        self.case_facts = case_facts
        self.assignments = assignments
        self.sql = []
        self._index = 0

    def execute(self, sql, params):
        self.sql.append(" ".join(sql.split()))

    def fetchone(self):
        self._index += 1
        return self.case_facts

    def fetchall(self):
        self._index += 1
        return self.assignments


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self):
        return self

    def __enter__(self):
        return self.cursor_obj

    def __exit__(self, *_):
        return False

    def close(self):
        self.closed = True


def install_fake_connection(monkeypatch, case_facts=CASE_FACTS, assignments=None):
    cursor = FakeCursor(case_facts, assignments or [assignment(1)])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(contracts, "get_connection", lambda: connection)
    return cursor, connection


def test_contract_context_uses_formal_assignment_not_orders_staff_id(monkeypatch):
    cursor, connection = install_fake_connection(monkeypatch)

    result = contracts.get_staff_contract_context("115000001")

    assert result["order"]["case_no"] == "115000001"
    assert result["assignment"]["assignment_id"] == 1
    assert result["staff"]["name"] == "月嫂1"
    assert result["client"]["identity_status"] == "一般市民"
    assert result["beclass"]["query_no"] == "115000001"
    assert "orders.staff_id" not in " ".join(cursor.sql)
    assert "v_order_details" not in " ".join(cursor.sql)
    assert "c.identity_status AS client_identity_status" in " ".join(cursor.sql)
    assert "clients.identity_status" not in " ".join(cursor.sql)
    assert connection.closed is True


def test_multiple_active_assignments_require_explicit_assignment_id(monkeypatch):
    install_fake_connection(monkeypatch, assignments=[assignment(1), assignment(2)])

    with pytest.raises(HTTPException) as error:
        contracts.get_staff_contract_context("115000001")

    assert error.value.status_code == 422
    assert "assignment_id" in error.value.detail


def test_assignment_id_selects_the_requested_formal_assignment(monkeypatch):
    install_fake_connection(monkeypatch, assignments=[assignment(1), assignment(2)])

    result = contracts.get_staff_contract_context("115000001", assignment_id=2)

    assert result["assignment"]["assignment_id"] == 2
    assert result["staff"]["name"] == "月嫂2"

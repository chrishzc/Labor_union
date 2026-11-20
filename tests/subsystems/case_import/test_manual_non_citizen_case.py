"""
File: test_manual_non_citizen_case.py
Description: 非市民手動建新案與年度配號驗證。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from infrastructure.mysql.non_citizen_case_number_repository import (
    allocate_non_citizen_case_number,
    preview_non_citizen_case_number,
)
from subsystems.case_import import non_citizen_registration_application


_REQUIRED_DETAILS = {
    "baby_info": "單胞胎",
    "email": "synthetic@example.test",
    "refund_bank_code": "0000001",
    "refund_account_no": "000000000001",
}


class _FakeCursor:
    def __init__(self, fetchone_results=None, fetchall_results=None):
        self._fetchone_results = list(fetchone_results or [])
        self._fetchall_results = list(fetchall_results or [])
        self.executed_queries: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, sql, params=()):
        self.executed_queries.append((sql, params))

    def fetchone(self):
        return self._fetchone_results.pop(0) if self._fetchone_results else None

    def fetchall(self):
        return self._fetchall_results.pop(0) if self._fetchall_results else []

    def close(self):
        pass


class _FakeConnection:
    def __init__(self, cursor_instance):
        self._cursor = cursor_instance
        self.began = False
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def begin(self):
        self.began = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


@pytest.fixture
def manual_case_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies.admin_auth import require_admin
    from api.routes.registration_applications import router
    from subsystems.access.authentication_session import AdminPrincipal

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        id=1, username="testadmin", display_name="Admin", role="admin"
    )
    return TestClient(app)


@pytest.mark.parametrize(
    ("birth_date", "stored_birth_date", "requires_cooking", "survey_answer"),
    [("2000-01-01", "2000-01-01", True, "是"), ("", None, False, "否")],
)
@pytest.mark.parametrize("holiday_answer", [None, "是", "否"])
def test_manual_case_api_preserves_birth_date_cooking_and_holiday_preference(
    monkeypatch, manual_case_client, birth_date, stored_birth_date, requires_cooking, survey_answer, holiday_answer
):
    cursor = _FakeCursor(fetchone_results=[{"next_sequence": 1}])
    conn = _FakeConnection(cursor)
    workflow = Mock()
    workflow.preview.return_value.import_version = 0
    workflow.apply_in_current_uow.return_value.client_id = 101
    monkeypatch.setattr(non_citizen_registration_application, "CaseImportWorkflow", Mock(return_value=workflow))
    monkeypatch.setattr("infrastructure.mysql.mysql_adapter.get_connection", lambda: conn)

    response = manual_case_client.post("/api/v1/admin/registration-applications/manual-non-citizen", json={
        **_REQUIRED_DETAILS,
        "mode": "new",
        "name": "測試客戶",
        "phone": "0900000000",
        "service_start_date": "2024-05-01",
        "service_days": 10,
        "service_time": "09:00-17:00 (8小時)",
        "birth_date": birth_date,
        "requires_cooking": requires_cooking,
        **({"holiday_double_pay": holiday_answer} if holiday_answer is not None else {}),
    })

    assert response.status_code == 200
    receipt = response.json()["data"]
    assert receipt["case_no"].endswith("001")
    intent = workflow.apply_in_current_uow.call_args.args[0].intent
    assert intent.order.requires_cooking is requires_cooking
    beclass_params = next(params for sql, params in cursor.executed_queries if sql.startswith("INSERT INTO beclass_records"))
    assert beclass_params[2] == stored_birth_date
    survey = json.loads(beclass_params[-1])
    assert survey["是否需要下廚"] == survey_answer
    holiday_field = "三節假日是否願意支付雙倍薪水"
    assert (holiday_field in survey) is (holiday_answer is not None)
    assert survey.get(holiday_field) == holiday_answer
    assert receipt["client_id"] == 101
    assert conn.committed
    assert receipt["virtual_account"].endswith("501")


@pytest.mark.parametrize(("service_time", "hours", "start", "end"), [
    ("08:00-17:00 (8小時)", 8, "08:00", "17:00"),
    ("08:00-16:00 (8小時)", 8, "08:00", "16:00"),
    ("08:30-17:00 (8小時)", 8, "08:30", "17:00"),
    ("08:30-16:30 (4小時)", 4, "08:30", "16:30"),
    ("08:00-12:00 (4小時)", 4, "08:00", "12:00"),
])
def test_manual_case_preserves_selected_hours_when_window_includes_rest(
    monkeypatch, manual_case_client, service_time, hours, start, end
):
    cursor = _FakeCursor(fetchone_results=[{"next_sequence": 1}])
    conn = _FakeConnection(cursor)
    workflow = Mock()
    workflow.preview.return_value.import_version = 0
    workflow.apply_in_current_uow.return_value.client_id = 101
    monkeypatch.setattr(non_citizen_registration_application, "CaseImportWorkflow", Mock(return_value=workflow))
    monkeypatch.setattr("infrastructure.mysql.mysql_adapter.get_connection", lambda: conn)
    response = manual_case_client.post("/api/v1/admin/registration-applications/manual-non-citizen", json={
        **_REQUIRED_DETAILS, "name": "測試客戶", "phone": "0900000000",
        "service_start_date": "2026-12-01", "service_days": 10, "service_time": service_time,
    })
    assert response.status_code == 200
    intent = workflow.apply_in_current_uow.call_args.args[0].intent
    assert intent.order.service_hours_per_day == hours
    assert intent.order.service_start_time.strftime("%H:%M") == start
    assert intent.order.service_end_time.strftime("%H:%M") == end
    assert conn.committed


@pytest.mark.parametrize(("field", "value", "error_field"), [
    ("service_time", "29:00-18:00 (8小時)", "服務時段"),
    ("service_time", "09:00-18:00 (108小時)", "服務時段"),
    ("service_time", "09:00-18:00 (1.2小時)", "服務時段"),
    ("service_time", "08:30-16:00 (8小時)", "服務時段"),
    ("service_time", "08:30-12:00 (4小時)", "服務時段"),
    ("service_time", "20:00-04:00 (8小時)", "服務時段"),
    ("baby_info", "第一胎", "胎數"),
    ("email", "name@example", "電子郵件"),
    ("refund_bank_code", "123", "退款銀行代號"),
    ("refund_bank_code", "00000001", "退款銀行代號"),
    ("refund_account_no", "abc", "退款銀行帳號"),
])
def test_manual_case_rejects_invalid_format_before_writing(
    monkeypatch, manual_case_client, field, value, error_field
):
    cursor = _FakeCursor()
    conn = _FakeConnection(cursor)
    monkeypatch.setattr("infrastructure.mysql.mysql_adapter.get_connection", lambda: conn)

    payload = {
        **_REQUIRED_DETAILS,
        "name": "測試客戶",
        "phone": "0900000000",
        "service_start_date": "2026-12-01",
        "service_days": 10,
        "service_time": "09:00-17:00 (8小時)",
    }
    response = manual_case_client.post(
        "/api/v1/admin/registration-applications/manual-non-citizen",
        json={**payload, field: value},
    )

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["code"] == "manual_non_citizen_invalid"
    assert error_field in error["message"]
    assert not cursor.executed_queries
    assert not conn.committed


@pytest.mark.parametrize("field", _REQUIRED_DETAILS)
@pytest.mark.parametrize("value", [None, "", "  "])
def test_manual_case_rejects_missing_details_before_writing(
    monkeypatch, manual_case_client, field, value
):
    conn = _FakeConnection(_FakeCursor())
    monkeypatch.setattr("infrastructure.mysql.mysql_adapter.get_connection", lambda: conn)
    payload = {
        **_REQUIRED_DETAILS,
        "name": "測試客戶",
        "phone": "0900000000",
        "service_start_date": "2026-12-01",
        "service_days": 10,
        "service_time": "09:00-17:00 (8小時)",
    }
    if value is None:
        del payload[field]
    else:
        payload[field] = value
    response = manual_case_client.post(
        "/api/v1/admin/registration-applications/manual-non-citizen", json=payload
    )
    assert response.status_code == 422
    assert not conn.began
    assert not conn._cursor.executed_queries


def test_number_preview_and_allocation_skip_existing_case_and_account():
    instant = datetime(2026, 11, 11, tzinfo=timezone.utc)
    results = [{"next_sequence": 1}, (1,), None, None, (1,), None, None, None]
    preview_cursor = _FakeCursor(fetchone_results=results)
    assert preview_non_citizen_case_number(_FakeConnection(preview_cursor), instant) == ("A115003", "99781699115503")
    assert all(sql.startswith("SELECT") and "FOR UPDATE" not in sql for sql, _ in preview_cursor.executed_queries)

    write_cursor = _FakeCursor(fetchone_results=results)
    assert allocate_non_citizen_case_number(_FakeConnection(write_cursor), instant) == "A115003"
    assert "FOR UPDATE" in write_cursor.executed_queries[1][0]
    assert write_cursor.executed_queries[-1][1] == (4, 115)


def test_manual_new_case_uses_server_number_without_legacy_mapping(monkeypatch, manual_case_client):
    preview_conn = _FakeConnection(_FakeCursor())
    cursor = _FakeCursor(fetchone_results=[{"next_sequence": 2}])
    conn = _FakeConnection(cursor)
    workflow = Mock()
    workflow.preview.return_value.import_version = 0
    workflow.apply_in_current_uow.return_value.client_id = 101
    monkeypatch.setattr(non_citizen_registration_application, "CaseImportWorkflow", Mock(return_value=workflow))
    connections = iter([preview_conn, conn])
    monkeypatch.setattr("infrastructure.mysql.mysql_adapter.get_connection", lambda: next(connections))
    path = "/api/v1/admin/registration-applications/manual-non-citizen"
    preview_response = manual_case_client.get(f"{path}/next-number")
    assert preview_response.status_code == 200
    estimate = preview_response.json()["data"]
    assert estimate["case_no"].endswith("001")
    assert estimate["virtual_account"].endswith("501")
    assert not preview_conn.committed

    response = manual_case_client.post(path, json={
        **_REQUIRED_DETAILS,
        "mode": "new",
        "name": "測試客戶",
        "phone": "0900000000",
        "service_start_date": "2026-12-01",
        "service_days": 10,
        "service_time": "09:00-17:00 (8小時)",
    })

    assert response.status_code == 200
    receipt = response.json()["data"]
    assert receipt["case_no"].endswith("002")
    assert receipt["virtual_account"].endswith("502")
    assert conn.committed
    assert not any(sql.startswith("INSERT INTO client_legacy_virtual_accounts") for sql, _ in cursor.executed_queries)


def test_historical_manual_creation_and_duplicate_check_are_retired(manual_case_client):
    path = "/api/v1/admin/registration-applications/manual-non-citizen"
    payload = {
        **_REQUIRED_DETAILS,
        "name": "測試客戶",
        "phone": "0900000000",
        "service_start_date": "2026-12-01",
        "service_days": 10,
        "service_time": "09:00-17:00 (8小時)",
    }
    assert manual_case_client.post(path, json={**payload, "mode": "historical"}).status_code == 422
    assert manual_case_client.post(path, json={**payload, "case_no": "A115001"}).status_code == 422
    assert manual_case_client.post(f"{path}/check", json={}).status_code in (404, 405)


def test_manual_case_copies_saved_beclass_details_without_overwriting_new_form(monkeypatch, manual_case_client):
    from domains.case_import.order_information import project_order_information

    cursor = _FakeCursor(fetchone_results=[{"next_sequence": 1}])
    conn = _FakeConnection(cursor)
    workflow = Mock()
    workflow.preview.return_value.import_version = 0
    workflow.apply_in_current_uow.return_value.client_id = 101
    monkeypatch.setattr(non_citizen_registration_application, "CaseImportWorkflow", Mock(return_value=workflow))
    monkeypatch.setattr("infrastructure.mysql.mysql_adapter.get_connection", lambda: conn)
    care = {"dietary_habits": "清淡", "maternal_allergy": "花生", "special_care_notes": "已保存照護說明",
            "vegetarian_preference": False, "alcohol_ratio": 0, "parking_space_provided": True,
            "other_babies_present": "是", "multi_birth_count": None}
    response = manual_case_client.post("/api/v1/admin/registration-applications/manual-non-citizen", json={
        **_REQUIRED_DETAILS, "name": "新案姓名", "phone": "0900000000",
        "service_start_date": "2026-12-01", "service_days": 10, "service_time": "09:00-17:00 (8小時)",
        "beclass_details": {**care, "tel": "030000000", "ext": "123", "zip_code": "300", "admin_notes": "來源報名備註"},
    })
    assert response.status_code == 200
    sql, params = next((sql, params) for sql, params in cursor.executed_queries if sql.startswith("INSERT INTO beclass_records"))
    assert sql.count("%s") == len(params)
    survey = json.loads(params[-1])
    values = project_order_information(survey).values
    assert {key: values[key] for key in care if key != "multi_birth_count"} == {key: value for key, value in care.items() if key != "multi_birth_count"}
    assert values["multi_birth_count"] == "單胞胎"
    assert params[0] == "新案姓名"
    assert params[-5:-1] == ("030000000", "123", "300", "來源報名備註")
    assert conn.committed


def test_manual_case_rejects_unowned_copy_fields_before_writing(monkeypatch, manual_case_client):
    conn = _FakeConnection(_FakeCursor())
    monkeypatch.setattr("infrastructure.mysql.mysql_adapter.get_connection", lambda: conn)
    response = manual_case_client.post("/api/v1/admin/registration-applications/manual-non-citizen", json={
        **_REQUIRED_DETAILS, "name": "測試客戶", "phone": "0900000000",
        "service_start_date": "2026-12-01", "service_days": 10, "service_time": "09:00-17:00 (8小時)",
        "beclass_details": {"line_user_id": "not-a-binding"},
    })
    assert response.status_code == 422
    assert not conn.began
    assert not conn.committed
    assert not conn._cursor.executed_queries

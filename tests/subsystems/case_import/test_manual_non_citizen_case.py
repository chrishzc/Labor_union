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
def test_manual_case_api_preserves_birth_date_and_cooking(
    monkeypatch, manual_case_client, birth_date, stored_birth_date, requires_cooking, survey_answer
):
    cursor = _FakeCursor(fetchone_results=[{"next_sequence": 1}])
    conn = _FakeConnection(cursor)
    workflow = Mock()
    workflow.preview.return_value.import_version = 0
    workflow.apply_in_current_uow.return_value.client_id = 101
    monkeypatch.setattr(non_citizen_registration_application, "CaseImportWorkflow", Mock(return_value=workflow))
    monkeypatch.setattr("infrastructure.mysql.mysql_adapter.get_connection", lambda: conn)

    response = manual_case_client.post("/api/v1/admin/registration-applications/manual-non-citizen", json={
        "mode": "new",
        "name": "測試客戶",
        "phone": "0900000000",
        "service_start_date": "2024-05-01",
        "service_days": 10,
        "service_time": "09:00-18:00 (8小時)",
        "birth_date": birth_date,
        "requires_cooking": requires_cooking,
    })

    assert response.status_code == 200
    receipt = response.json()["data"]
    assert receipt["case_no"].endswith("001")
    intent = workflow.apply_in_current_uow.call_args.args[0].intent
    assert intent.order.requires_cooking is requires_cooking
    beclass_params = next(params for sql, params in cursor.executed_queries if sql.startswith("INSERT INTO beclass_records"))
    assert beclass_params[2] == stored_birth_date
    assert json.loads(beclass_params[-1])["是否需要下廚"] == survey_answer
    assert receipt["client_id"] == 101
    assert conn.committed
    assert receipt["virtual_account"].endswith("501")


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
        "mode": "new",
        "name": "測試客戶",
        "phone": "0900000000",
        "service_start_date": "2026-12-01",
        "service_days": 10,
        "service_time": "09:00-18:00 (8小時)",
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
        "name": "測試客戶",
        "phone": "0900000000",
        "service_start_date": "2026-12-01",
        "service_days": 10,
        "service_time": "09:00-18:00 (8小時)",
    }
    assert manual_case_client.post(path, json={**payload, "mode": "historical"}).status_code == 422
    assert manual_case_client.post(path, json={**payload, "case_no": "A115001"}).status_code == 422
    assert manual_case_client.post(f"{path}/check", json={}).status_code in (404, 405)

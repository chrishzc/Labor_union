"""
File: test_manual_non_citizen_case.py
Description: 歷史非市民案件手動建案、欄位驗證、案號與虛擬帳號重複檢查及覆蓋邏輯單元測試。
"""

from __future__ import annotations

from datetime import date, datetime
import pytest

from subsystems.case_import.non_citizen_registration_application import (
    check_case_accounting_details,
    check_case_number_duplicate,
    check_virtual_account_conflict,
    create_manual_non_citizen_case,
)


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


def test_check_case_number_duplicate():
    cursor_found = _FakeCursor(fetchone_results=[{"case_no": "A113001"}])
    assert check_case_number_duplicate(cursor_found, "A113001") is True

    cursor_not_found = _FakeCursor(fetchone_results=[None])
    assert check_case_number_duplicate(cursor_not_found, "A113002") is False


def test_check_case_accounting_details():
    # Scenario 1: Case has received cash and ledger entries
    cursor_with_accounting = _FakeCursor(
        fetchone_results=[
            {"received_total_ntd": 18000},
            {"cnt": 2},
            {"cnt": 1},
        ]
    )
    has_details, received, summary = check_case_accounting_details(cursor_with_accounting, "113000001")
    assert has_details is True
    assert received == 18000
    assert "已有帳務紀錄" in summary
    assert "18,000" in summary

    # Scenario 2: Cancelled case with 0 cash and 0 ledger entries
    cursor_empty = _FakeCursor(
        fetchone_results=[
            {"received_total_ntd": 0},
            {"cnt": 0},
            {"cnt": 0},
        ]
    )
    has_details_empty, received_empty, summary_empty = check_case_accounting_details(cursor_empty, "113000002")
    assert has_details_empty is False
    assert received_empty == 0
    assert summary_empty == "無帳務明細與收款紀錄"


def test_check_virtual_account_conflict_invalid_format():
    cursor = _FakeCursor()
    with pytest.raises(ValueError, match="虛擬帳號格式不正確"):
        check_virtual_account_conflict(cursor, "123456")
    with pytest.raises(ValueError, match="虛擬帳號格式不正確"):
        check_virtual_account_conflict(cursor, "997816991130")


def test_check_virtual_account_conflict_no_conflict():
    # 1. No legacy mapping (fetchone returns None)
    # 2. Formula case exists? (fetchone returns None)
    cursor = _FakeCursor(fetchone_results=[None, None])
    result = check_virtual_account_conflict(cursor, "99781699113501")
    assert result["conflict"] is False
    assert result["conflict_case_no"] is None
    assert result["has_accounting_details"] is False


def test_check_virtual_account_conflict_legacy_mapping_found():
    # 1. Legacy mapping returns conflicting case
    # 2. Order info query returns status
    # 3. Accounting query (received_total, ledger_count, paid_count)
    cursor = _FakeCursor(
        fetchone_results=[
            {"case_no": "113000001"},
            {"case_no": "113000001", "status": "訂單取消", "cancel_reason": "無意願", "name": "張小姐", "phone": "0912345678"},
            {"received_total_ntd": 0},
            {"cnt": 0},
            {"cnt": 0},
        ]
    )
    result = check_virtual_account_conflict(cursor, "99781699113001")
    assert result["conflict"] is True
    assert result["conflict_case_no"] == "113000001"
    assert result["conflict_case_status"] == "訂單取消"
    assert result["cancel_reason"] == "無意願"
    assert result["conflict_case_client_name"] == "張小姐"
    assert result["has_accounting_details"] is False
    assert result["accounting_description"] == "無帳務明細與收款紀錄"


def test_create_manual_non_citizen_case_validation():
    conn = _FakeConnection(_FakeCursor())
    valid_payload = {
        "case_no": "A113099",
        "virtual_account": "99781699113599",
        "name": "陳小美",
        "phone": "0912345678",
        "service_start_date": "2024-05-01",
        "service_days": 10,
        "service_time": "09:00-18:00 (8小時)",
    }

    # Missing case_no
    with pytest.raises(ValueError, match="請輸入案件編號"):
        create_manual_non_citizen_case(conn, {**valid_payload, "case_no": ""}, "admin")

    # Missing virtual_account
    with pytest.raises(ValueError, match="請輸入虛擬帳號"):
        create_manual_non_citizen_case(conn, {**valid_payload, "virtual_account": ""}, "admin")

    # Missing name
    with pytest.raises(ValueError, match="請輸入客戶姓名"):
        create_manual_non_citizen_case(conn, {**valid_payload, "name": ""}, "admin")

    # Invalid phone
    with pytest.raises(ValueError, match="連絡電話格式不正確"):
        create_manual_non_citizen_case(conn, {**valid_payload, "phone": "123"}, "admin")

    # Missing service_start_date
    with pytest.raises(ValueError, match="請輸入預計服務開始日"):
        create_manual_non_citizen_case(conn, {**valid_payload, "service_start_date": ""}, "admin")

    # Invalid service_days
    with pytest.raises(ValueError, match="服務天數必須為大於 0 的整數"):
        create_manual_non_citizen_case(conn, {**valid_payload, "service_days": 0}, "admin")

    # Invalid service_time
    with pytest.raises(ValueError, match="服務時段格式不正確"):
        create_manual_non_citizen_case(conn, {**valid_payload, "service_time": "早上"}, "admin")


def test_manual_non_citizen_routes_check_and_create(monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import app
    from api.dependencies.admin_auth import require_admin
    from subsystems.access.authentication_session import AdminPrincipal

    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        id=1, username="testadmin", display_name="Admin", role="admin"
    )

    try:
        # Mock get_connection to avoid connecting to real DB in route unit test
        monkeypatch.setattr(
            "infrastructure.mysql.mysql_adapter.get_connection",
            lambda: _FakeConnection(_FakeCursor()),
        )
        import subsystems.case_import.non_citizen_registration_application as app_module
        monkeypatch.setattr(app_module, "check_case_number_duplicate", lambda cursor, case_no: False)
        monkeypatch.setattr(
            app_module,
            "check_virtual_account_conflict",
            lambda cursor, va, current_case_no=None: {
                "conflict": True,
                "virtual_account": va,
                "conflict_case_no": "113000088",
                "conflict_case_status": "訂單取消",
                "conflict_case_client_name": "取消者",
                "conflict_case_client_phone": "0988000000",
                "has_accounting_details": False,
                "received_total_ntd": 0,
                "accounting_description": "無帳務明細與收款紀錄",
                "cancel_reason": "無服務意願",
            },
        )

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/admin/registration-applications/manual-non-citizen/check",
                json={"virtual_account": "99781699113588", "case_no": "A113088"},
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["conflict"] is True
            assert data["conflict_case_no"] == "113000088"
            assert data["conflict_case_status"] == "訂單取消"
            assert data["has_accounting_details"] is False

            # Test duplicate case_no
            monkeypatch.setattr(app_module, "check_case_number_duplicate", lambda cursor, case_no: True)
            resp_dup = client.post(
                "/api/v1/admin/registration-applications/manual-non-citizen/check",
                json={"virtual_account": "99781699113588", "case_no": "A113088"},
            )
            assert resp_dup.status_code == 422
            assert "已存在" in str(resp_dup.json()["detail"])

            # Test create route
            monkeypatch.setattr(
                app_module,
                "create_manual_non_citizen_case",
                lambda connection, payload, actor: {
                    "case_no": payload["case_no"],
                    "virtual_account": payload["virtual_account"],
                    "client_id": 999,
                    "overridden_case_no": "113000088" if payload.get("override_conflict") else None,
                    "message": f"歷史非市民案件「{payload['case_no']}」建立成功。",
                },
            )

            resp_create = client.post(
                "/api/v1/admin/registration-applications/manual-non-citizen",
                json={
                    "case_no": "A113088",
                    "virtual_account": "99781699113588",
                    "name": "歷史補登者",
                    "phone": "0912345678",
                    "service_start_date": "2024-05-01",
                    "service_days": 10,
                    "service_time": "09:00-18:00 (8小時)",
                    "override_conflict": True,
                    "override_case_no": "113000088",
                },
            )
            assert resp_create.status_code == 200
            create_data = resp_create.json()["data"]
            assert create_data["case_no"] == "A113088"
            assert create_data["virtual_account"] == "99781699113588"
            assert create_data["overridden_case_no"] == "113000088"
    finally:
        app.dependency_overrides.pop(require_admin, None)

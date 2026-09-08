"""Contract tests for the bounded, authenticated Staff roster profile."""

from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_profile import get_staff_profile_application
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes.staff import router
from infrastructure.mysql.staff_profile_query_repository import (
    MySqlStaffProfileQueryRepository,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.profile_query import StaffProfileQueryApplication


RAW_IDENTITY_CARD = "A123456789"
RAW_EMERGENCY_PHONE = "0987654321"


def _row():
    return {
        "id": 7,
        "registered_at": datetime(2026, 1, 2, 3, 4, 5),
        "identity_card": RAW_IDENTITY_CARD,
        "phone": "0912345678",
        "tel": "035551234",
        "tel_ext": "66",
        "email": "staff@example.test",
        "birthday": date(1980, 1, 2),
        "city": "新竹市",
        "zip_code": "300",
        "address": "北區測試路 1 號",
        "education": "大學",
        "emergency_contact_name": "王家人",
        "emergency_contact_phone": RAW_EMERGENCY_PHONE,
        "admin_notes": "僅供內部排班聯絡",
    }


class _Repository:
    def fetch(self, _staff_id):
        return _row()

    def fetch_bank_accounts(self, _staff_id):
        return (
            {
                "id": 3,
                "bank_code": "812",
                "branch_code": "0012",
                "account_no": "123456789012",
                "is_primary": 1,
            },
            {
                "id": 4,
                "bank_code": "004",
                "branch_code": "0001",
                "account_no": "987654321098",
                "is_primary": 0,
            },
        )


def _client():
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        9, "staff-reader", "Staff Reader", "system_admin"
    )
    app.dependency_overrides[get_staff_profile_application] = lambda: (
        StaffProfileQueryApplication(_Repository())
    )
    return TestClient(app)


def test_staff_profile_returns_complete_internal_admin_fields():
    response = _client().get(
        "/api/v1/staff/7/profile",
        headers={"X-Correlation-ID": "staff-profile-01"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["staff_id"] == 7
    assert payload["identity_card"] == "A123456789"
    assert payload["emergency_contact_phone"] == "0987654321"
    assert payload["birthday"] == "1980-01-02"
    assert payload["email"] == "staff@example.test"
    assert payload["address"] == "北區測試路 1 號"
    assert payload["admin_notes"] == "僅供內部排班聯絡"
    assert payload["bank_accounts"] == [
        {
            "account_id": 3,
            "bank_code": "812",
            "branch_code": "0012",
            "account_no": "123456789012",
            "is_primary": True,
        },
        {
            "account_id": 4,
            "bank_code": "004",
            "branch_code": "0001",
            "account_no": "987654321098",
            "is_primary": False,
        },
    ]
    serialized = response.text
    assert RAW_IDENTITY_CARD in serialized
    assert RAW_EMERGENCY_PHONE in serialized
    assert "ip_address" not in payload
    assert "line_user_id" not in payload


class _Cursor:
    def __init__(self, *, one=None, many=()):
        self.sql = ""
        self.params = ()
        self._one = one
        self._many = many

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _Connection:
    def __init__(self):
        self.cursors = [
            _Cursor(one=_row()),
            _Cursor(many=({"id": 3, "bank_code": "812", "branch_code": "0012", "account_no": "123456789012", "is_primary": 1},)),
        ]
        self.created_cursors = []

    def cursor(self):
        cursor = self.cursors.pop(0)
        self.created_cursors.append(cursor)
        return cursor


def test_staff_profile_repository_reads_only_the_bounded_detail_columns():
    connection = _Connection()
    repository = MySqlStaffProfileQueryRepository(connection)
    row = repository.fetch(7)
    accounts = repository.fetch_bank_accounts(7)

    assert row is not None
    assert accounts[0]["account_no"] == "123456789012"
    assert connection.cursors == []
    profile_cursor, bank_cursor = connection.created_cursors
    assert profile_cursor.params == (7,)
    assert "WHERE id=%s LIMIT 1" in profile_cursor.sql
    assert "ip_address" not in profile_cursor.sql
    assert "line_user_id" not in profile_cursor.sql
    assert "account_no" not in profile_cursor.sql
    assert bank_cursor.params == (7,)
    assert "FROM staff_bank_accounts WHERE staff_id=%s" in bank_cursor.sql
    assert "ORDER BY is_primary DESC,id ASC LIMIT 21" in bank_cursor.sql


def test_staff_profile_treats_blank_optional_database_values_as_not_recorded():
    row = _row()
    row.update({"tel": " ", "tel_ext": "", "admin_notes": ""})

    class _BlankRepository(_Repository):
        def fetch(self, _staff_id):
            return row

    profile = StaffProfileQueryApplication(_BlankRepository()).query(7)

    assert profile.identity_card == RAW_IDENTITY_CARD
    assert profile.telephone is None
    assert profile.telephone_extension is None
    assert profile.admin_notes is None

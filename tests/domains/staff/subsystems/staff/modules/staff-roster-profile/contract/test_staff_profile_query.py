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
    serialized = response.text
    assert RAW_IDENTITY_CARD in serialized
    assert RAW_EMERGENCY_PHONE in serialized
    assert "ip_address" not in payload
    assert "line_user_id" not in payload


class _Cursor:
    def __init__(self):
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return _row()


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()

    def cursor(self):
        return self.cursor_instance


def test_staff_profile_repository_reads_only_the_bounded_detail_columns():
    connection = _Connection()
    row = MySqlStaffProfileQueryRepository(connection).fetch(7)

    assert row is not None
    assert connection.cursor_instance.params == (7,)
    sql = connection.cursor_instance.sql
    assert "WHERE id=%s LIMIT 1" in sql
    assert "ip_address" not in sql
    assert "line_user_id" not in sql
    assert "account_no" not in sql

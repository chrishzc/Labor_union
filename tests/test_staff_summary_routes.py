"""
File: test_staff_summary_routes.py
Description: 驗證 Staff 摘要 route 的管理員會話、typed 參數衝突與 bounded cursor 回應。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.routes import staff as staff_routes
from subsystems.access.authentication_session import AdminPrincipal


class _Cursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        self.executed = (query, params)

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def _app(*, authenticated: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(staff_routes.router)
    if authenticated:
        app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
            7,
            "staff-reader",
            "Staff Reader",
            "admin",
        )
    return app


def test_missing_session_is_rejected_before_database_access(monkeypatch):
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setattr(
        staff_routes.db_service,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("DB must not be called")),
    )

    response = TestClient(_app(authenticated=False)).get(
        "/api/v1/staff/summaries"
    )

    assert response.status_code == 401


def test_conflicting_cursor_parameters_return_typed_validation_error():
    response = TestClient(_app(authenticated=True)).get(
        "/api/v1/staff/summaries",
        params={"after_id": 1, "staff_id": 2},
    )

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["category"] == "validation"
    assert error["code"] == "staff_summary_query_params_conflict"
    assert error["correlation_id"] == "staff-summary-query"


def test_authorized_query_returns_bounded_cursor_page(monkeypatch):
    connection = _Connection(
        [
            {"id": 11, "name": "去敏人員甲", "phone": None},
            {"id": 12, "name": None, "phone": "09********"},
            {"id": 13, "name": "下一頁人員", "phone": None},
        ]
    )
    monkeypatch.setattr(
        staff_routes.db_service,
        "get_connection",
        lambda: connection,
    )

    response = TestClient(_app(authenticated=True)).get(
        "/api/v1/staff/summaries",
        params={"page_size": 2, "after_id": 10},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [
            {"id": 11, "name": "去敏人員甲", "phone": None},
            {"id": 12, "name": None, "phone": "09********"},
        ],
        "next_cursor": 12,
    }
    assert connection.cursor_instance.executed[1] == (10, 3)
    assert connection.closed is True


def test_retired_unbounded_endpoint_remains_gone():
    response = TestClient(_app(authenticated=False)).get("/api/v1/staff")

    assert response.status_code == 410


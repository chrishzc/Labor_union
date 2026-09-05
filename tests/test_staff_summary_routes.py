"""
File: test_staff_summary_routes.py
Description: 驗證 Staff 摘要 route 的管理員會話、typed 參數衝突與 bounded cursor 回應。
"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_summary import get_staff_summary_application
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import staff as staff_routes
from infrastructure.mysql.staff_summary_query_repository import (
    MySqlStaffSummaryQueryRepository,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.summary_query import (
    StaffSummaryQueryApplication,
    StaffSummaryQueryService,
)


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


def _query_application(connection):
    return StaffSummaryQueryApplication(
        StaffSummaryQueryService(MySqlStaffSummaryQueryRepository(connection))
    )


def _app(*, authenticated: bool, query_application=None, query_connection=None) -> FastAPI:
    app = FastAPI()
    app.include_router(staff_routes.router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    if authenticated:
        app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
            7,
            "staff-reader",
            "Staff Reader",
            "admin",
        )
    if query_application is not None:
        def override_application():
            try:
                yield query_application
            finally:
                if query_connection is not None:
                    query_connection.close()

        app.dependency_overrides[get_staff_summary_application] = override_application
    return app


def _app_with_disabled_principal() -> FastAPI:
    app = FastAPI()
    app.include_router(staff_routes.router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)

    def reject_disabled_principal():
        raise HTTPException(status_code=403, detail="目前身分無權執行此操作")

    app.dependency_overrides[require_admin] = reject_disabled_principal
    return app


def test_missing_session_is_rejected_before_database_access(monkeypatch):
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")

    response = TestClient(_app(authenticated=False)).get(
        "/api/v1/staff/summaries"
    )

    assert response.status_code == 401


def test_conflicting_cursor_parameters_return_typed_validation_error():
    connection = _Connection([])
    response = TestClient(
        _app(
            authenticated=True,
            query_application=_query_application(connection),
            query_connection=connection,
        )
    ).get(
        "/api/v1/staff/summaries",
        params={"after_id": 1, "staff_id": 2},
        headers={"X-Correlation-ID": "staff-summary-conflict-01"},
    )

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["category"] == "validation"
    assert error["code"] == "staff_summary_query_params_conflict"
    assert error["correlation_id"] == "staff-summary-conflict-01"
    assert response.headers["X-Correlation-ID"] == "staff-summary-conflict-01"


def test_disabled_principal_is_rejected_with_global_typed_error():
    response = TestClient(_app_with_disabled_principal()).get(
        "/api/v1/staff/summaries",
        headers={"X-Correlation-ID": "staff-summary-disabled-01"},
    )

    assert response.status_code == 403
    error = response.json()["detail"]["error"]
    assert error["category"] == "forbidden"
    assert error["correlation_id"] == "staff-summary-disabled-01"
    assert response.headers["X-Correlation-ID"] == "staff-summary-disabled-01"


def test_authorized_query_returns_bounded_cursor_page():
    connection = _Connection(
        [
            {"id": 11, "name": "去敏人員甲", "phone": None, "education": "護理系"},
            {"id": 12, "name": None, "phone": "09********", "education": None},
            {"id": 13, "name": "下一頁人員", "phone": None, "education": "幼保系"},
        ]
    )
    response = TestClient(
        _app(
            authenticated=True,
            query_application=_query_application(connection),
            query_connection=connection,
        )
    ).get(
        "/api/v1/staff/summaries",
        params={"page_size": 2, "after_id": 10},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [
            {"id": 11, "name": "去敏人員甲", "phone": None, "education": "護理系"},
            {"id": 12, "name": None, "phone": "09********", "education": None},
        ],
        "next_cursor": 12,
    }
    assert connection.cursor_instance.executed[1] == (10, 3)
    assert connection.closed is True


def test_retired_unbounded_endpoint_remains_gone():
    response = TestClient(_app(authenticated=False)).get("/api/v1/staff")

    assert response.status_code == 410

"""
File: test_leave_substitution_assignment_query.py
Description: 驗證請假代班 assignment query 的最小 schedule projection、單一查詢、排序與管理員授權。
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.leave_substitution import get_leave_substitution_application
from api.routes.leave_substitution import router
from api.schemas.leave_substitution import LeaveAssignmentSummaryView
from infrastructure.mysql.leave_substitution_repository import (
    MySqlLeaveSubstitutionRepository,
)
from subsystems.access.authentication_session import AdminPrincipal


_ASSIGNMENT = {
    "assignment_id": 31,
    "staff_id": 11,
    "assigned_start_date": "2026-08-01",
    "assigned_end_date": "2026-08-05",
    "official_schedules": [
        {"schedule_id": 301, "work_date": "2026-08-03"},
    ],
}


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, _error_type, _error, _traceback):
        return False

    def execute(self, statement, params):
        self.executions.append((" ".join(statement.split()), params))

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance


class _Application:
    def __init__(self, assignments=()):
        self.assignments = assignments
        self.calls = []

    def list_effective_assignments(self, case_no):
        self.calls.append(case_no)
        return self.assignments


def _app(application: _Application) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_leave_substitution_application] = lambda: application
    return app


@pytest.mark.parametrize(
    "invalid_schedule",
    (
        {"work_date": "2026-08-03"},
        {"schedule_id": 301},
        {"schedule_id": None, "work_date": "2026-08-03"},
        {"schedule_id": 301, "work_date": "2026-08-03", "extra": True},
    ),
)
def test_assignment_schedule_projection_is_closed_and_required(invalid_schedule):
    valid = LeaveAssignmentSummaryView.model_validate(_ASSIGNMENT)

    assert valid.official_schedules[0].schedule_id == 301
    with pytest.raises(ValidationError):
        LeaveAssignmentSummaryView.model_validate(
            {**_ASSIGNMENT, "official_schedules": [invalid_schedule]}
        )


def test_repository_groups_official_schedules_with_one_stably_ordered_query():
    connection = _Connection(
        [
            {
                "id": 31,
                "staff_id": 11,
                "assigned_start_date": date(2026, 8, 1),
                "assigned_end_date": date(2026, 8, 5),
                "schedule_id": 301,
                "work_date": date(2026, 8, 3),
            },
            {
                "id": 31,
                "staff_id": 11,
                "assigned_start_date": date(2026, 8, 1),
                "assigned_end_date": date(2026, 8, 5),
                "schedule_id": 302,
                "work_date": date(2026, 8, 4),
            },
            {
                "id": 32,
                "staff_id": 12,
                "assigned_start_date": date(2026, 8, 6),
                "assigned_end_date": date(2026, 8, 7),
                "schedule_id": None,
                "work_date": None,
            },
        ]
    )

    result = MySqlLeaveSubstitutionRepository(
        connection
    ).list_effective_assignments("CASE-LEAVE-1")

    assert result == (
        {
            "id": 31,
            "staff_id": 11,
            "assigned_start_date": date(2026, 8, 1),
            "assigned_end_date": date(2026, 8, 5),
            "official_schedules": (
                {"schedule_id": 301, "work_date": date(2026, 8, 3)},
                {"schedule_id": 302, "work_date": date(2026, 8, 4)},
            ),
        },
        {
            "id": 32,
            "staff_id": 12,
            "assigned_start_date": date(2026, 8, 6),
            "assigned_end_date": date(2026, 8, 7),
            "official_schedules": (),
        },
    )
    assert len(connection.cursor_instance.executions) == 1
    statement, params = connection.cursor_instance.executions[0]
    assert "LEFT JOIN staff_schedule" in statement
    assert "s.generation_id=g.effective_generation_id" in statement
    assert "s.effective_marker=1" in statement
    assert "s.is_work_day=1" in statement
    assert "ORDER BY a.assignment_sequence,a.id,s.work_date,s.id" in statement
    assert params == ("CASE-LEAVE-1",)


def test_route_projects_only_closed_assignment_and_schedule_fields(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "local_bypass")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    application = _Application(
        (
            {
                "id": 31,
                "staff_id": 11,
                "assigned_start_date": date(2026, 8, 1),
                "assigned_end_date": date(2026, 8, 5),
                "official_schedules": (
                    {"schedule_id": 301, "work_date": date(2026, 8, 3)},
                ),
                "internal_generation": 99,
            },
        )
    )

    response = TestClient(_app(application)).get(
        "/api/v1/orders/CASE-LEAVE-1/leave-substitution/assignments"
    )

    assert response.status_code == 200
    assert response.json()["data"] == [_ASSIGNMENT]
    assert application.calls == ["CASE-LEAVE-1"]


def test_route_keeps_401_and_403_admin_boundary(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    unauthenticated_app = _app(_Application())

    unauthenticated = TestClient(unauthenticated_app).get(
        "/api/v1/orders/CASE-LEAVE-1/leave-substitution/assignments"
    )

    assert unauthenticated.status_code == 401

    forbidden_app = _app(_Application())
    forbidden_app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        None,
        "leave-viewer",
        "請假唯讀人員",
        "line_viewer",
        capabilities=frozenset(),
    )
    forbidden = TestClient(forbidden_app).get(
        "/api/v1/orders/CASE-LEAVE-1/leave-substitution/assignments"
    )

    assert forbidden.status_code == 403

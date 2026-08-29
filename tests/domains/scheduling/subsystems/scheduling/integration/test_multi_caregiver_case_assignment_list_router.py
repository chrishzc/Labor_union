"""
File: test_multi_caregiver_case_assignment_list_router.py
Description: 驗證 case 與 staff 正式指派唯讀路由及 typed Calendar option。
"""

from datetime import date

import pytest
from fastapi import HTTPException

from api.routes import multi_caregiver_case_assignments as router_module
from subsystems.scheduling.multi_caregiver_schedule_query import (
    CaseAssignmentQuery,
    StaffAssignmentOption,
)


class _Application:
    def __init__(self, *, case_result=None, staff_result=(), error=None):
        self.case_result = case_result or CaseAssignmentQuery((), None)
        self.staff_result = staff_result
        self.error = error
        self.case_received = []
        self.staff_received = []

    def list_case_assignments(self, case_no):
        self.case_received.append(case_no)
        if self.error:
            raise self.error
        return self.case_result

    def list_staff_assignments(self, staff_id):
        self.staff_received.append(staff_id)
        if self.error:
            raise self.error
        return self.staff_result


def test_list_route_delegates_only_case_no(monkeypatch):
    application = _Application()

    response = router_module.list_case_schedule_assignments(
        "115000001", principal=object(), application=application
    )

    assert application.case_received == ["115000001"]
    assert response.success is True
    assert response.data.assignments == []


def test_staff_list_route_delegates_only_staff_id(monkeypatch):
    application = _Application(
        staff_result=(StaffAssignmentOption(
            id=21,
            case_no="115000001",
            staff_id=31,
            status="active",
            assigned_start_date=date(2026, 8, 1),
            assigned_end_date=date(2026, 8, 10),
            order_status="服務中",
            actual_start_date=date(2026, 8, 1),
            actual_end_date=None,
            staff_name="測試月嫂",
        ),),
    )

    response = router_module.list_staff_schedule_assignments(
        31, principal=object(), application=application
    )

    assert application.staff_received == [31]
    assert response.success is True


def test_list_route_maps_validation_to_bad_request(monkeypatch):
    application = _Application(error=ValueError("case_no must be a non-empty string"))

    with pytest.raises(HTTPException) as error:
        router_module.list_case_schedule_assignments(
            "115000001", principal=object(), application=application
        )

    assert error.value.status_code == 400
    assert error.value.detail == "case_no must be a non-empty string"


def test_list_route_maps_unexpected_error_to_internal_server_error(monkeypatch):
    application = _Application(error=RuntimeError("database unavailable"))

    with pytest.raises(HTTPException) as error:
        router_module.list_case_schedule_assignments(
            "115000001", principal=object(), application=application
        )

    assert error.value.status_code == 500
    assert error.value.detail == "Failed to retrieve case assignments"

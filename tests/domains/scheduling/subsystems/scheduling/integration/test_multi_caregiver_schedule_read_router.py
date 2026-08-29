import pytest
from fastapi import HTTPException
from datetime import date
from decimal import Decimal

from api.routes import multi_caregiver_schedule_read as router_module
from subsystems.scheduling.multi_caregiver_schedule_query import (
    AssignmentScheduleAssignment,
    AssignmentScheduleGuard,
    AssignmentScheduleQuery,
)


def _query(assignment_id=31):
    return AssignmentScheduleQuery(
        assignment=AssignmentScheduleAssignment(
            id=assignment_id,
            case_no="115000001",
            staff_id=7,
            status="active",
            assigned_start_date=date(2026, 8, 1),
            assigned_end_date=date(2026, 8, 10),
            planned_hours=Decimal("100"),
            actual_hours=Decimal("0"),
            service_hours_per_day=Decimal("10"),
            staff_name="測試月嫂",
            client_name="測試客戶",
        ),
        schedule_days=(),
        database_current_date=date(2026, 8, 29),
        adjustment_guard=AssignmentScheduleGuard(False, False, False, ()),
    )


class _Application:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.received = []

    def get_assignment_schedule(self, assignment_id):
        self.received.append(assignment_id)
        if self.error:
            raise self.error
        return self.result


def test_get_route_delegates_only_assignment_id(monkeypatch):
    application = _Application(_query())
    response = router_module.get_assignment_schedule(31, principal=object(), application=application)

    assert application.received == [31]
    assert response.success is True
    assert response.data.assignment.id == 31


def test_get_route_maps_validation_to_bad_request(monkeypatch):
    application = _Application(error=ValueError("assignment does not exist"))

    with pytest.raises(HTTPException) as error:
        router_module.get_assignment_schedule(31, principal=object(), application=application)

    assert error.value.status_code == 400
    assert error.value.detail == "assignment does not exist"


def test_get_route_maps_unexpected_error_to_internal_server_error(monkeypatch):
    application = _Application(error=RuntimeError("database unavailable"))

    with pytest.raises(HTTPException) as error:
        router_module.get_assignment_schedule(31, principal=object(), application=application)

    assert error.value.status_code == 500
    assert error.value.detail == "Failed to retrieve assignment schedule"

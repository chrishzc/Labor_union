from datetime import date

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routes import multi_caregiver_schedule as router_module


def test_generate_route_delegates_only_assignment_id(monkeypatch):
    received = []
    monkeypatch.setattr(
        router_module,
        "generate_assignment_schedule_service",
        lambda assignment_id: received.append(assignment_id) or {"actual_hours": 18},
    )

    response = router_module.generate_assignment_schedule(31)

    assert received == [31]
    assert response.success is True
    assert response.data == {"actual_hours": 18}


def test_generate_route_maps_validation_to_bad_request(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "generate_assignment_schedule_service",
        lambda _assignment_id: (_ for _ in ()).throw(ValueError("date overlap")),
    )

    with pytest.raises(HTTPException) as error:
        router_module.generate_assignment_schedule(31)

    assert error.value.status_code == 400
    assert error.value.detail == "date overlap"


def test_generate_route_maps_unexpected_error_to_internal_server_error(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "generate_assignment_schedule_service",
        lambda _assignment_id: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    with pytest.raises(HTTPException) as error:
        router_module.generate_assignment_schedule(31)

    assert error.value.status_code == 500
    assert error.value.detail == "Failed to generate assignment schedule"


def test_adjust_route_delegates_only_assignment_owned_inputs(monkeypatch):
    received = {}

    def adjust(**kwargs):
        received.update(kwargs)
        return {"actual_hours": 9}

    monkeypatch.setattr(router_module, "adjust_assignment_schedule_day", adjust)
    response = router_module.adjust_assignment_schedule(
        router_module.AssignmentScheduleDayAdjustment(
            is_work_day=False,
            is_double_pay=True,
            notes="leave",
        ),
        assignment_id=31,
        work_date=date(2026, 7, 5),
    )

    assert received == {
        "assignment_id": 31,
        "work_date": date(2026, 7, 5),
        "is_work_day": False,
        "is_double_pay": True,
        "notes": "leave",
    }
    assert response.data == {"actual_hours": 9}


def test_adjustment_body_rejects_client_owned_identity_or_hours():
    with pytest.raises(ValidationError):
        router_module.AssignmentScheduleDayAdjustment(
            is_work_day=True,
            is_double_pay=False,
            case_no="CASE-1",
        )

    with pytest.raises(ValidationError):
        router_module.AssignmentScheduleDayAdjustment(
            is_work_day=True,
            is_double_pay=False,
            actual_hours=99,
        )


def test_adjust_route_maps_validation_to_bad_request(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "adjust_assignment_schedule_day",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("schedule locked")),
    )

    with pytest.raises(HTTPException) as error:
        router_module.adjust_assignment_schedule(
            router_module.AssignmentScheduleDayAdjustment(
                is_work_day=False,
                is_double_pay=False,
            ),
            assignment_id=31,
            work_date=date(2026, 7, 5),
        )

    assert error.value.status_code == 400
    assert error.value.detail == "schedule locked"

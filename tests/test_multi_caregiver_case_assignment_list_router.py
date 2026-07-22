import pytest
from fastapi import HTTPException

from api.routes import multi_caregiver_case_assignments as router_module


def test_list_route_delegates_only_case_no(monkeypatch):
    received = []
    monkeypatch.setattr(
        router_module,
        "list_case_schedule_assignments_service",
        lambda case_no: received.append(case_no) or {"assignments": [{"id": 21}]},
    )

    response = router_module.list_case_schedule_assignments("115000001")

    assert received == ["115000001"]
    assert response.success is True
    assert response.data == {"assignments": [{"id": 21}]}


def test_list_route_maps_validation_to_bad_request(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "list_case_schedule_assignments_service",
        lambda _case_no: (_ for _ in ()).throw(ValueError("case_no must be a non-empty string")),
    )

    with pytest.raises(HTTPException) as error:
        router_module.list_case_schedule_assignments("115000001")

    assert error.value.status_code == 400
    assert error.value.detail == "case_no must be a non-empty string"


def test_list_route_maps_unexpected_error_to_internal_server_error(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "list_case_schedule_assignments_service",
        lambda _case_no: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    with pytest.raises(HTTPException) as error:
        router_module.list_case_schedule_assignments("115000001")

    assert error.value.status_code == 500
    assert error.value.detail == "Failed to retrieve case assignments"

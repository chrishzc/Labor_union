import pytest
from fastapi import HTTPException

from api.routes import multi_caregiver_schedule_read as router_module


def test_get_route_delegates_only_assignment_id(monkeypatch):
    received = []
    monkeypatch.setattr(
        router_module,
        "get_assignment_schedule_service",
        lambda assignment_id: received.append(assignment_id) or {"assignment": {"id": assignment_id}},
    )

    response = router_module.get_assignment_schedule(31)

    assert received == [31]
    assert response.success is True
    assert response.data == {"assignment": {"id": 31}}


def test_get_route_maps_validation_to_bad_request(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "get_assignment_schedule_service",
        lambda _assignment_id: (_ for _ in ()).throw(ValueError("assignment does not exist")),
    )

    with pytest.raises(HTTPException) as error:
        router_module.get_assignment_schedule(31)

    assert error.value.status_code == 400
    assert error.value.detail == "assignment does not exist"


def test_get_route_maps_unexpected_error_to_internal_server_error(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "get_assignment_schedule_service",
        lambda _assignment_id: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    with pytest.raises(HTTPException) as error:
        router_module.get_assignment_schedule(31)

    assert error.value.status_code == 500
    assert error.value.detail == "Failed to retrieve assignment schedule"

"""Regression coverage for the synchronization endpoints registered on the FastAPI app."""

from fastapi.testclient import TestClient

from api.main import app


def test_assignment_synchronization_preview_route_is_registered_on_main_app():
    response = TestClient(app).post(
        "/api/v1/orders/C-1/assignment-synchronization/preview",
        json={},
    )

    assert response.status_code == 422
    assert response.status_code != 404

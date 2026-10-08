"""Regression coverage for the unauthenticated LINE root health response."""

from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from line import line_bot


def _root_client():
    app = FastAPI()
    app.include_router(line_bot.router)
    return TestClient(app)


def test_root_health_hides_database_connection_exception(monkeypatch):
    private_error = "host=db.internal.example port=3306 user=worker password=example"
    acquire = Mock(side_effect=RuntimeError(private_error))
    monkeypatch.setattr(line_bot, "get_db_connection", acquire)

    with _root_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "api_version": "1.0.0",
        "database": {"connected": False, "message": "database_unavailable"},
    }
    assert private_error not in response.text
    acquire.assert_called_once_with()


def test_root_health_keeps_success_response_and_closes_connection(monkeypatch):
    conn = Mock()
    monkeypatch.setattr(line_bot, "get_db_connection", Mock(return_value=conn))

    with _root_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "api_version": "1.0.0",
        "database": {"connected": True, "message": "Database connected"},
    }
    conn.close.assert_called_once_with()

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.performance import ApiPerformanceMiddleware


def test_timing_headers_are_ephemeral_and_do_not_write_slow_request_output(capsys):
    application = FastAPI()
    application.add_middleware(ApiPerformanceMiddleware)

    @application.get("/summary")
    def query_summary():
        return {"status": "ok"}

    response = TestClient(application).get("/summary")

    assert response.status_code == 200
    assert response.headers["server-timing"].startswith("application;dur=")
    assert float(response.headers["x-response-time-ms"]) >= 0
    assert capsys.readouterr().out == ""


def test_mutating_response_remains_non_cacheable():
    application = FastAPI()
    application.add_middleware(ApiPerformanceMiddleware)

    @application.post("/apply")
    def apply_change():
        return {"status": "accepted"}

    response = TestClient(application).post("/apply")

    assert response.headers["cache-control"] == "no-store"

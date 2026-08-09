from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.routes import system_status
from subsystems.access.authentication_session import AdminPrincipal


def test_system_admin_can_read_non_persistent_performance_snapshot(monkeypatch):
    app = FastAPI()
    app.include_router(system_status.router)
    app.dependency_overrides[require_system_admin] = _system_admin
    monkeypatch.setattr(system_status.api_performance_snapshot, "snapshot", _snapshot)

    response = TestClient(app).get("/api/v1/system/status/performance-snapshot")

    assert response.status_code == 200
    assert response.json()["data"]["request_count"] == 4
    assert response.json()["data"]["p95_response_time_upper_bound_ms"] == 5000


def _system_admin() -> AdminPrincipal:
    return AdminPrincipal(id=1, username="admin", display_name="Admin", role="system_admin")


def _snapshot():
    from shared_kernel.performance_snapshot import ApiPerformanceSnapshot
    from datetime import UTC, datetime

    return ApiPerformanceSnapshot(datetime(2026, 8, 9, tzinfo=UTC), 4, 725.0, 250, 5000, 2100.0)

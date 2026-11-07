"""Readonly backup owner projection: no SQL, dump, restore or scheduler effects."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.routes import database_backup as routes
from scripts import nas_database_maintenance as owner


def _client(monkeypatch, tmp_path, settings=None):
    monkeypatch.setattr(owner, "SCHEDULE", tmp_path / "absent-schedule.json")
    monkeypatch.setattr(owner, "LOCAL_STATUS", tmp_path / "absent-status.json")
    def missing_settings():
        raise owner.MaintenanceBlocked("not configured")
    monkeypatch.setattr(owner, "load_settings", (lambda: settings) if settings else missing_settings)
    def forbidden(*_args, **_kwargs):
        pytest.fail("readiness performed a backup, SQL, restore or schedule effect")
    for name in ("backup", "restore", "configure_daily_backup", "run_windows_powershell"):
        if hasattr(owner, name): monkeypatch.setattr(owner, name, forbidden)
    monkeypatch.setattr(routes, "configure_daily_backup", forbidden)
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(routes.data_center_router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=7)
    return TestClient(app)


def test_declared_data_center_backup_readiness_reuses_the_original_owner_without_configuration(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        original = client.get("/api/v1/system/database-backup")
        current = client.get("/api/v1/data-center/backup/readiness")
    assert original.status_code == current.status_code == 200
    assert current.json() == original.json()
    result = current.json()["data"]
    assert result["configured"] is result["storage_ready"] is result["disaster_recovery_ready"] is False
    assert result["last_backup"] is None
    assert not list(tmp_path.iterdir())


def test_readable_storage_is_not_promoted_to_backup_integrity_or_disaster_recovery(monkeypatch, tmp_path):
    root = tmp_path / "existing-backup-root"
    root.mkdir()
    settings = {"backup_root": root, "host": "synthetic-private-target", "port": 3306}
    with _client(monkeypatch, tmp_path, settings) as client:
        response = client.get("/api/v1/data-center/backup/readiness")
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["configured"] is result["storage_ready"] is True
    assert result["disaster_recovery_ready"] is False and result["last_backup"] is None
    assert "synthetic-private-target" not in response.text
    assert not list(root.iterdir())


def test_malformed_original_schedule_is_typed_unavailable_without_repairing_or_running_it(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    schedule = tmp_path / "broken.json"
    schedule.write_text("{broken")
    monkeypatch.setattr(owner, "SCHEDULE", schedule)
    with client:
        response = client.get("/api/v1/data-center/backup/readiness")
    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "backup_status_unavailable"
    assert response.json()["detail"]["error"]["retryable"] is True
    assert schedule.read_text() == "{broken"


def test_data_center_backup_readiness_keeps_authentication_and_has_no_mutation_route():
    from fastapi import HTTPException
    app = FastAPI(); app.include_router(routes.data_center_router)
    def denied(): raise HTTPException(401, "authentication required")
    app.dependency_overrides[require_admin] = denied
    with TestClient(app) as client:
        assert client.get("/api/v1/data-center/backup/readiness").status_code == 401
        assert client.post("/api/v1/data-center/backup/readiness").status_code == 405

"""
File: test_react_admin_production_wiring.py
Description: 驗證 production FastAPI React mount helper、private health route與實際呼叫見證。
"""

from __future__ import annotations

import inspect
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import main as api_main
from infrastructure.runtime.react_admin_artifact import (
    load_react_admin_runtime_from_environment,
)
from scripts.build_react_admin_artifact import build_artifact


def _artifact(tmp_path: Path, name: str) -> Path:
    source = tmp_path / f"source-{name}"
    source.mkdir()
    (source / "index.html").write_text(
        f'<div id="root"></div><script src="/admin/app-{name}.js"></script>',
        encoding="utf-8",
    )
    (source / f"app-{name}.js").write_text(name, encoding="utf-8")
    output = tmp_path / name
    build_artifact(output, source=source, source_ref=name)
    return output


def _runtime(tmp_path: Path):
    current = _artifact(tmp_path, "current")
    previous = _artifact(tmp_path, "previous")
    runtime = load_react_admin_runtime_from_environment(
        {
            "APP_ENV": "production",
            "REACT_ADMIN_CURRENT_ARTIFACT_DIR": str(current),
            "REACT_ADMIN_PREVIOUS_ARTIFACT_DIR": str(previous),
            "REACT_ADMIN_ACTIVE_SELECTOR": "current",
        },
        workspace_root=tmp_path,
    )
    assert runtime is not None
    return runtime


def test_production_mount_helper_is_fail_closed_and_serves_validated_artifact(
    tmp_path: Path,
) -> None:
    unconfigured = FastAPI()
    assert api_main.mount_react_admin_static(unconfigured, None) is False
    assert all(getattr(route, "path", None) != "/admin" for route in unconfigured.routes)
    assert not hasattr(unconfigured.state, "react_admin_artifact_health")

    configured = FastAPI()
    runtime = _runtime(tmp_path)
    assert api_main.mount_react_admin_static(configured, runtime) is True
    assert sum(getattr(route, "path", None) == "/admin" for route in configured.routes) == 1
    assert configured.state.react_admin_artifact_health()["healthy"] is True
    with TestClient(configured) as client:
        assert client.get("/admin/").status_code == 200
        assert client.get("/admin/app-current.js").text == "current"
        assert client.get("/admin/not-listed.js").status_code == 404


def test_global_app_registers_authenticated_private_health_and_production_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shared_key = "phase6b-production-wiring-key-0001"
    runtime = _runtime(tmp_path)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", shared_key)
    monkeypatch.setattr(
        api_main.app.state,
        "react_admin_artifact_health",
        runtime.health_attestation,
        raising=False,
    )
    with TestClient(api_main.app) as client:
        private_response = client.get(
            "/internal/v1/runtime/react-admin/artifact-health"
        )
        authorized_response = client.get(
            "/internal/v1/runtime/react-admin/artifact-health",
            headers={
                "X-Internal-Service-Key": shared_key,
                "X-Internal-Service-Name": "phase6b-verifier",
            },
        )
        public_alias = client.get("/api/v1/react-admin/artifact-health")
    assert private_response.status_code == 401
    assert authorized_response.status_code == 200
    assert authorized_response.json()["data"]["healthy"] is True
    assert public_alias.status_code == 404
    source = inspect.getsource(api_main)
    assert "mount_react_admin_static(app, REACT_ADMIN_RUNTIME)" in source

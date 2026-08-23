"""
File: test_react_admin_static_hosting.py
Description: 驗證 React 管理端 immutable artifact 的掛載與路徑隔離。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import FastAPI
from starlette.testclient import TestClient

from infrastructure.runtime.react_admin_artifact import (
    ReactAdminStaticApplication,
    validate_react_admin_artifact,
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_artifact(root: Path, *, version: str = "current-v1") -> Path:
    files = {
        "index.html": (
            '<!doctype html><html><body><div id="root"></div>'
            '<script type="module" src="/admin/assets/app-12345678.js"></script>'
            '<link rel="stylesheet" href="/admin/assets/app-12345678.css">'
            "</body></html>"
        ).encode("utf-8"),
        "assets/app-12345678.js": b"console.log('admin');\n",
        "assets/app-12345678.css": b"#root { display: block; }\n",
        "assets/logo.svg": b"<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>\n",
    }
    root.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    for relative_path, content in sorted(files.items()):
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        rows.append(
            {
                "path": relative_path,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    manifest_without_digest: dict[str, object] = {
        "contract": "react-admin-artifact/v1",
        "artifact_version": version,
        "source_ref": "test-source",
        "build_tools": {"test": "pytest"},
        "api_compatibility_revision": "react-admin-api-v1",
        "root_entry": "index.html",
        "files": rows,
    }
    manifest = {
        **manifest_without_digest,
        "artifact_digest": hashlib.sha256(
            _canonical_json(manifest_without_digest)
        ).hexdigest(),
    }
    (root / "artifact-manifest.json").write_bytes(_canonical_json(manifest))
    return root


def _application(artifact_root: Path) -> FastAPI:
    artifact = validate_react_admin_artifact(artifact_root)
    application = FastAPI()

    @application.get("/api/ping")
    def api_ping() -> dict[str, str]:
        return {"status": "api-preserved"}

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "health-preserved"}

    @application.get("/internal/ping")
    def internal_ping() -> dict[str, str]:
        return {"status": "internal-preserved"}

    application.mount(
        "/admin",
        ReactAdminStaticApplication(artifact),
        name="react-admin",
    )
    return application


def test_admin_mount_serves_only_manifest_proven_assets(tmp_path: Path) -> None:
    application = _application(_write_artifact(tmp_path / "artifact"))

    with TestClient(application) as client:
        root_response = client.get("/admin/")
        manifest_response = client.get("/admin/artifact-manifest.json")
        script_response = client.get("/admin/assets/app-12345678.js")
        css_response = client.get("/admin/assets/app-12345678.css")
        unknown_response = client.get("/admin/assets/not-listed.js")
        fallback_response = client.get("/admin/unknown-route")

    assert root_response.status_code == 200
    assert '<div id="root"></div>' in root_response.text
    assert manifest_response.status_code == 200
    assert manifest_response.headers["cache-control"] == "no-store"
    assert script_response.status_code == 200
    assert css_response.status_code == 200
    assert unknown_response.status_code == 404
    assert fallback_response.status_code == 404
    assert "<div id=\"root\"></div>" not in unknown_response.text
    assert "<div id=\"root\"></div>" not in fallback_response.text


def test_admin_mount_does_not_intercept_existing_api_health_or_internal_paths(
    tmp_path: Path,
) -> None:
    application = _application(_write_artifact(tmp_path / "artifact"))

    with TestClient(application) as client:
        api_response = client.get("/api/ping")
        health_response = client.get("/health")
        internal_response = client.get("/internal/ping")
        admin_api_response = client.get("/admin/api/ping")

    assert api_response.status_code == 200
    assert api_response.json() == {"status": "api-preserved"}
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "health-preserved"}
    assert internal_response.status_code == 200
    assert internal_response.json() == {"status": "internal-preserved"}
    assert admin_api_response.status_code == 404


def test_admin_mount_rejects_mutation_methods(tmp_path: Path) -> None:
    application = _application(_write_artifact(tmp_path / "artifact"))

    with TestClient(application) as client:
        response = client.post("/admin/")

    assert response.status_code == 405


def test_admin_manifest_drift_fails_closed(tmp_path: Path) -> None:
    artifact_root = _write_artifact(tmp_path / "artifact")
    application = _application(artifact_root)
    manifest = artifact_root / "artifact-manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")

    with TestClient(application) as client:
        response = client.get("/admin/artifact-manifest.json")

    assert response.status_code == 404

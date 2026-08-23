"""
File: test_react_admin_security_headers.py
Description: 驗證 React 管理端靜態檔案的 CSP、MIME 與快取邊界。
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


def _write_artifact(root: Path) -> Path:
    files = {
        "index.html": (
            '<!doctype html><html><body><div id="root"></div>'
            '<script type="module" src="/admin/assets/app-12345678.js"></script>'
            '<link rel="stylesheet" href="/admin/assets/app-12345678.css">'
            "</body></html>"
        ).encode("utf-8"),
        "assets/app-12345678.js": b"export default {};\n",
        "assets/app-12345678.css": b"#root { color: black; }\n",
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
        "artifact_version": "security-v1",
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
    application = FastAPI()
    application.mount(
        "/admin",
        ReactAdminStaticApplication(validate_react_admin_artifact(artifact_root)),
        name="react-admin",
    )
    return application


def test_admin_responses_have_required_security_headers(tmp_path: Path) -> None:
    application = _application(_write_artifact(tmp_path / "artifact"))

    with TestClient(application) as client:
        responses = [
            client.get("/admin/"),
            client.get("/admin/artifact-manifest.json"),
            client.get("/admin/assets/app-12345678.js"),
            client.get("/admin/assets/app-12345678.css"),
            client.get("/admin/assets/missing.js"),
        ]

    for response in responses:
        csp = response.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "script-src 'self'" in csp
        assert "unsafe-eval" not in csp
        assert "http://" not in csp
        assert "https://" not in csp
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_admin_cache_and_mime_contract_distinguishes_root_and_hashed_assets(
    tmp_path: Path,
) -> None:
    application = _application(_write_artifact(tmp_path / "artifact"))

    with TestClient(application) as client:
        root_response = client.get("/admin/")
        manifest_response = client.get("/admin/artifact-manifest.json")
        script_response = client.get("/admin/assets/app-12345678.js")
        css_response = client.get("/admin/assets/app-12345678.css")
        unversioned_response = client.get("/admin/assets/logo.svg")

    assert root_response.headers["cache-control"] == "no-store"
    assert manifest_response.headers["cache-control"] == "no-store"
    assert script_response.headers["cache-control"] == (
        "public, max-age=31536000, immutable"
    )
    assert css_response.headers["cache-control"] == (
        "public, max-age=31536000, immutable"
    )
    assert unversioned_response.headers["cache-control"] == "no-store"
    assert root_response.headers["content-type"].startswith("text/html")
    assert manifest_response.headers["content-type"].startswith("application/json")
    assert script_response.headers["content-type"].split(";")[0] in {
        "application/javascript",
        "text/javascript",
    }
    assert css_response.headers["content-type"].startswith("text/css")
    assert unversioned_response.headers["content-type"].startswith("image/svg+xml")

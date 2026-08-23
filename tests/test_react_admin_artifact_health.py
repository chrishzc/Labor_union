"""
File: test_react_admin_artifact_health.py
Description: 驗證 React 管理端 current/previous artifact health attestation 與 fail-closed。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from infrastructure.runtime import react_admin_artifact
from infrastructure.runtime.react_admin_artifact import (
    ReactAdminArtifactError,
    load_react_admin_runtime_from_environment,
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_artifact(root: Path, *, version: str) -> Path:
    files = {
        "index.html": b'<html><body><div id="root"></div></body></html>',
        "assets/app-12345678.js": b"export default {};\n",
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


def _environment(current: Path, previous: Path, selector: str = "current") -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "REACT_ADMIN_CURRENT_ARTIFACT_DIR": str(current),
        "REACT_ADMIN_PREVIOUS_ARTIFACT_DIR": str(previous),
        "REACT_ADMIN_ACTIVE_SELECTOR": selector,
    }


def test_runtime_attests_only_the_selected_artifact_identity(tmp_path: Path) -> None:
    current = _write_artifact(tmp_path / "current", version="current-v1")
    previous = _write_artifact(tmp_path / "previous", version="previous-v1")

    runtime = load_react_admin_runtime_from_environment(
        _environment(current, previous),
        workspace_root=tmp_path,
    )

    assert runtime is not None
    attestation = runtime.health_attestation()
    assert set(attestation) == {
        "active_selector",
        "artifact_version",
        "artifact_digest",
        "manifest_digest",
        "api_compatibility_revision",
        "root_marker_checked",
        "checked_asset_digest",
        "healthy",
    }
    assert attestation["active_selector"] == "current"
    assert attestation["artifact_version"] == "current-v1"
    assert attestation["root_marker_checked"] is True
    assert attestation["healthy"] is True
    assert str(tmp_path) not in json.dumps(attestation, ensure_ascii=False)


def test_production_startup_loads_registry_before_artifact_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_registry() -> None:
        raise ReactAdminArtifactError("registry-first")

    monkeypatch.setattr(
        react_admin_artifact, "_load_compatibility_registry", reject_registry
    )

    with pytest.raises(ReactAdminArtifactError, match="registry-first"):
        load_react_admin_runtime_from_environment({"APP_ENV": "production"})


def test_runtime_can_rehearse_previous_selector_without_changing_api_identity(
    tmp_path: Path,
) -> None:
    current = _write_artifact(tmp_path / "current", version="current-v1")
    previous = _write_artifact(tmp_path / "previous", version="previous-v1")

    runtime = load_react_admin_runtime_from_environment(
        _environment(current, previous, selector="previous"),
        workspace_root=tmp_path,
    )

    assert runtime is not None
    attestation = runtime.health_attestation()
    assert attestation["active_selector"] == "previous"
    assert attestation["artifact_version"] == "previous-v1"


@pytest.mark.parametrize(
    "mutate_environment",
    [
        lambda env, current, previous: env.update(
            REACT_ADMIN_ACTIVE_SELECTOR="unknown"
        ),
        lambda env, current, previous: env.update(
            REACT_ADMIN_PREVIOUS_ARTIFACT_DIR=str(current)
        ),
        lambda env, current, previous: env.update(
            REACT_ADMIN_PREVIOUS_ARTIFACT_DIR=str(previous / "missing")
        ),
    ],
    ids=["unknown-selector", "same-artifact", "missing-previous"],
)
def test_runtime_rejects_invalid_or_missing_previous_binding(
    tmp_path: Path,
    mutate_environment,
) -> None:
    current = _write_artifact(tmp_path / "current", version="current-v1")
    previous = _write_artifact(tmp_path / "previous", version="previous-v1")
    environment = _environment(current, previous)
    mutate_environment(environment, current, previous)

    with pytest.raises(ReactAdminArtifactError):
        load_react_admin_runtime_from_environment(environment, workspace_root=tmp_path)


def test_runtime_rejects_corrupt_previous_and_detects_active_asset_drift(
    tmp_path: Path,
) -> None:
    current = _write_artifact(tmp_path / "current", version="current-v1")
    previous = _write_artifact(tmp_path / "previous", version="previous-v1")
    (previous / "assets/app-12345678.js").write_bytes(b"tampered\n")

    with pytest.raises(ReactAdminArtifactError):
        load_react_admin_runtime_from_environment(
            _environment(current, previous),
            workspace_root=tmp_path,
        )

    valid_previous = _write_artifact(tmp_path / "previous-valid", version="previous-v2")
    runtime = load_react_admin_runtime_from_environment(
        _environment(current, valid_previous),
        workspace_root=tmp_path,
    )
    assert runtime is not None
    (current / "index.html").write_bytes(b"<html><div id=\"root\"></div></html>")

    with pytest.raises(ReactAdminArtifactError):
        runtime.health_attestation()


def test_runtime_rejects_manifest_digest_drift(tmp_path: Path) -> None:
    current = _write_artifact(tmp_path / "current", version="current-v1")
    previous = _write_artifact(tmp_path / "previous", version="previous-v1")
    runtime = load_react_admin_runtime_from_environment(
        _environment(current, previous),
        workspace_root=tmp_path,
    )

    assert runtime is not None
    manifest = current / "artifact-manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")

    with pytest.raises(ReactAdminArtifactError, match="manifest digest changed"):
        runtime.health_attestation()

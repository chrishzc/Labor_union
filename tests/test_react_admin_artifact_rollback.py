"""
File: test_react_admin_artifact_rollback.py
Description: 驗證 current/previous 切換、舊版無 immutable_assets 相容回復與 fail-closed 契約。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from infrastructure.runtime.react_admin_artifact import (
    PRIVATE_IMMUTABLE_CACHE_CONTROL,
    ReactAdminArtifactError,
    ReactAdminStaticApplication,
    load_react_admin_runtime_from_environment,
)
from scripts import build_react_admin_artifact as artifact_builder
from scripts.build_react_admin_artifact import build_artifact


def _artifact(tmp_path: Path, name: str) -> Path:
    source = tmp_path / f"source-{name}"
    source.mkdir()
    (source / "index.html").write_text(
        f'<!doctype html><div id="root"></div><p>{name}</p>', encoding="utf-8"
    )
    output = tmp_path / name
    build_artifact(output, source=source, source_ref=name)
    return output


def _environment(current: Path, previous: Path, selector: str) -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "REACT_ADMIN_CURRENT_ARTIFACT_DIR": str(current),
        "REACT_ADMIN_PREVIOUS_ARTIFACT_DIR": str(previous),
        "REACT_ADMIN_ACTIVE_SELECTOR": selector,
    }


def test_selector_rehearses_current_previous_current_without_data_changes(
    tmp_path: Path,
) -> None:
    current = _artifact(tmp_path, "current")
    previous = _artifact(tmp_path, "previous")

    first = load_react_admin_runtime_from_environment(
        _environment(current, previous, "current"), workspace_root=tmp_path
    )
    rolled_back = load_react_admin_runtime_from_environment(
        _environment(current, previous, "previous"), workspace_root=tmp_path
    )
    restored = load_react_admin_runtime_from_environment(
        _environment(current, previous, "current"), workspace_root=tmp_path
    )

    assert first is not None and rolled_back is not None and restored is not None
    assert first.active.artifact_digest == restored.active.artifact_digest
    assert first.active.artifact_digest != rolled_back.active.artifact_digest
    assert rolled_back.health_attestation()["active_selector"] == "previous"


@pytest.mark.parametrize("selector", ["", "unknown", "CURRENT"])
def test_unknown_or_missing_selector_fails_closed(tmp_path: Path, selector: str) -> None:
    current = _artifact(tmp_path, "current")
    previous = _artifact(tmp_path, "previous")

    with pytest.raises(ReactAdminArtifactError):
        load_react_admin_runtime_from_environment(
            _environment(current, previous, selector), workspace_root=tmp_path
        )


def test_same_or_corrupt_previous_fails_closed(tmp_path: Path) -> None:
    current = _artifact(tmp_path, "current")
    with pytest.raises(ReactAdminArtifactError, match="must differ"):
        load_react_admin_runtime_from_environment(
            _environment(current, current, "previous"), workspace_root=tmp_path
        )

    previous = _artifact(tmp_path, "previous")
    (previous / "index.html").write_text("corrupt", encoding="utf-8")
    with pytest.raises(ReactAdminArtifactError):
        load_react_admin_runtime_from_environment(
            _environment(current, previous, "previous"), workspace_root=tmp_path
        )


def test_environment_loader_rejects_symlink_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = _artifact(tmp_path, "current")
    previous = _artifact(tmp_path, "previous")
    linked = tmp_path / "linked-current"
    try:
        linked.symlink_to(current, target_is_directory=True)
    except OSError:
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == linked or original(path))
    with pytest.raises(ReactAdminArtifactError, match="cannot be a symlink or junction"):
        load_react_admin_runtime_from_environment(
            _environment(linked, previous, "current"), workspace_root=tmp_path
        )


def test_unconfigured_development_skips_mount_but_production_rejects() -> None:
    assert load_react_admin_runtime_from_environment({"APP_ENV": "development"}) is None
    with pytest.raises(ReactAdminArtifactError):
        load_react_admin_runtime_from_environment({"APP_ENV": "production"})


def test_rollback_to_legacy_v1_previous_artifact_succeeds_and_downgrades_cache_to_no_store(
    tmp_path: Path,
) -> None:
    current_source = tmp_path / "source-current-v2"
    (current_source / "assets").mkdir(parents=True)
    (current_source / ".vite").mkdir(parents=True)
    (current_source / "index.html").write_text(
        '<!doctype html><div id="root"></div><script src="/test/assets/app-11112222.js"></script>',
        encoding="utf-8",
    )
    (current_source / "assets/app-11112222.js").write_text("export const v = 2;\n", encoding="utf-8")
    (current_source / ".vite/manifest.json").write_text(
        json.dumps({"index.html": {"file": "assets/app-11112222.js", "isEntry": True}}),
        encoding="utf-8",
    )
    current = tmp_path / "current-v2"
    build_artifact(current, source=current_source, source_ref="release-v2")

    previous_source = tmp_path / "source-previous-v1"
    (previous_source / "assets").mkdir(parents=True)
    (previous_source / "index.html").write_text(
        '<!doctype html><div id="root"></div><script src="/test/assets/app-00001111.js"></script>',
        encoding="utf-8",
    )
    (previous_source / "assets/app-00001111.js").write_text("export const v = 1;\n", encoding="utf-8")
    previous = tmp_path / "previous-v1"
    build_artifact(previous, source=previous_source, source_ref="release-v1")
    manifest_path = previous / "artifact-manifest.json"
    legacy_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy_manifest.pop("immutable_assets")
    legacy_manifest.pop("artifact_digest")
    legacy_manifest["artifact_digest"] = artifact_builder._digest_bytes(
        artifact_builder._canonical_json(legacy_manifest)
    )
    manifest_path.write_bytes(artifact_builder._canonical_json(legacy_manifest))

    active_current = load_react_admin_runtime_from_environment(
        _environment(current, previous, "current"), workspace_root=tmp_path
    )
    rolled_back = load_react_admin_runtime_from_environment(
        _environment(current, previous, "previous"), workspace_root=tmp_path
    )
    assert active_current is not None and rolled_back is not None

    resp_current = TestClient(ReactAdminStaticApplication(active_current.active)).get(
        "/assets/app-11112222.js"
    )
    assert resp_current.status_code == 200
    assert resp_current.headers["cache-control"] == PRIVATE_IMMUTABLE_CACHE_CONTROL

    resp_previous = TestClient(ReactAdminStaticApplication(rolled_back.active)).get(
        "/assets/app-00001111.js"
    )
    assert resp_previous.status_code == 200
    assert resp_previous.headers["cache-control"] == "no-store"

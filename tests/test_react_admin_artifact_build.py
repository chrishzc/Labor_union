"""
File: test_react_admin_artifact_build.py
Description: 驗證 immutable React artifact 建置、root link拒絕與clean-workspace fail-closed契約。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.runtime.react_admin_artifact import (
    ReactAdminArtifactError,
    validate_react_admin_artifact,
)
from scripts import build_react_admin_artifact as artifact_builder
from scripts.build_react_admin_artifact import build_artifact


def _source(root: Path, marker: str = "current") -> Path:
    source = root / f"dist-{marker}"
    (source / "assets").mkdir(parents=True)
    (source / "index.html").write_text(
        '<!doctype html><div id="root"></div><script src="/admin/assets/index-abcdefgh.js"></script>',
        encoding="utf-8",
    )
    (source / "assets/index-abcdefgh.js").write_text(
        f"globalThis.__artifact = '{marker}'", encoding="utf-8"
    )
    return source


def test_build_creates_exact_versioned_manifest_without_overwrite(tmp_path: Path) -> None:
    source = _source(tmp_path)
    output = tmp_path / "artifacts" / "current"
    output.parent.mkdir()

    result = build_artifact(
        output,
        source=source,
        source_ref="release-current",
        api_compatibility_revision="react-admin-api-v1",
    )

    manifest = json.loads((output / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert result["healthy"] is True
    assert manifest["source_ref"] == "release-current"
    assert {row["path"] for row in manifest["files"]} == {
        "index.html",
        "assets/index-abcdefgh.js",
    }
    assert all(len(row["sha256"]) == 64 for row in manifest["files"])
    with pytest.raises(ReactAdminArtifactError, match="already exists"):
        build_artifact(output, source=source)


def test_non_production_build_uses_registry_active_revision_without_env_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    monkeypatch.setenv("REACT_ADMIN_API_COMPATIBILITY_REVISION", "unknown-env")

    build_artifact(tmp_path / "artifact", source=source)
    manifest = json.loads(
        (tmp_path / "artifact" / "artifact-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["source_ref"] == "working-tree"
    assert manifest["api_compatibility_revision"] == "react-admin-api-v1"


@pytest.mark.parametrize("mutation", ["extra", "missing", "mismatch"])
def test_validation_rejects_inventory_and_digest_drift(
    tmp_path: Path, mutation: str
) -> None:
    source = _source(tmp_path)
    output = tmp_path / "artifact"
    build_artifact(output, source=source)
    if mutation == "extra":
        (output / "unexpected.txt").write_text("drift", encoding="utf-8")
    elif mutation == "missing":
        (output / "assets/index-abcdefgh.js").unlink()
    else:
        (output / "assets/index-abcdefgh.js").write_text("tampered", encoding="utf-8")

    with pytest.raises(ReactAdminArtifactError):
        validate_react_admin_artifact(output, workspace_root=tmp_path)


def test_validation_rejects_root_marker_and_workspace_root(tmp_path: Path) -> None:
    source = _source(tmp_path)
    output = tmp_path / "artifact"
    build_artifact(output, source=source)

    with pytest.raises(ReactAdminArtifactError, match="workspace root"):
        validate_react_admin_artifact(output, workspace_root=output)

    (output / "index.html").write_text("<main>wrong root</main>", encoding="utf-8")
    with pytest.raises(ReactAdminArtifactError):
        validate_react_admin_artifact(output, workspace_root=tmp_path)


def test_validation_rejects_artifact_root_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    output = tmp_path / "artifact"
    build_artifact(output, source=source)
    linked = tmp_path / "linked-artifact"
    try:
        linked.symlink_to(output, target_is_directory=True)
    except OSError:
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == linked or original(path))
    with pytest.raises(ReactAdminArtifactError, match="real directory"):
        validate_react_admin_artifact(linked, workspace_root=tmp_path)


def test_clean_build_creates_dist_before_resolve_and_missing_output_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "ui" / "dist"
    output = tmp_path / "new" / "nested" / "current"

    def create_frontend_dist(output: Path) -> None:
        output.mkdir(parents=True, exist_ok=True)
        (output / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
        (output / "assets.js").write_text("ready", encoding="utf-8")

    monkeypatch.setattr(artifact_builder, "_run_frontend_build", create_frontend_dist)
    result = build_artifact(output, source=source, run_frontend_build=True)
    assert output.is_dir()
    assert result["healthy"] is True


def test_frontend_build_uses_locked_project_tools_and_isolated_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ui_root = tmp_path / "ui"
    tsc = ui_root / "node_modules/typescript/bin/tsc"
    vite = ui_root / "node_modules/vite/bin/vite.js"
    tsc.parent.mkdir(parents=True)
    vite.parent.mkdir(parents=True)
    tsc.write_text("", encoding="utf-8")
    vite.write_text("", encoding="utf-8")
    node = tmp_path / "node.exe"
    node.write_text("", encoding="utf-8")
    commands: list[list[str]] = []

    class Completed:
        returncode = 0

    monkeypatch.setattr(artifact_builder, "UI_ROOT", ui_root)
    monkeypatch.setattr(artifact_builder, "_node_executable", lambda: node)
    monkeypatch.setattr(
        artifact_builder.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command) or Completed(),
    )

    output = tmp_path / "isolated-dist"
    artifact_builder._run_frontend_build(output)

    assert commands == [
        [str(node), str(tsc), "-b"],
        [
            str(node),
            str(vite),
            "build",
            "--outDir",
            str(output),
            "--emptyOutDir",
        ],
    ]


def test_build_rejects_source_root_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    linked = tmp_path / "linked-source"
    try:
        linked.symlink_to(source, target_is_directory=True)
    except OSError:
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == linked or original(path))
    with pytest.raises(ReactAdminArtifactError, match="real directory"):
        build_artifact(tmp_path / "artifact", source=linked)

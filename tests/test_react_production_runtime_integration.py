"""
File: test_react_production_runtime_integration.py
Description: 驗證 Phase6B-RUN 本機 artifact preflight 與 fail-closed identity。
"""

from __future__ import annotations

from pathlib import Path

from scripts.build_react_admin_artifact import build_artifact
from scripts.launcher_preflight import inspect_profile


def _source(root: Path, marker: str) -> Path:
    root.mkdir()
    (root / "index.html").write_text(
        f'<div id="root"></div><script src="/admin/assets/app-{marker}.js"></script>',
        encoding="utf-8",
    )
    assets = root / "assets"
    assets.mkdir()
    (assets / f"app-{marker}.js").write_text(f"console.log('{marker}')", encoding="utf-8")
    return root


def test_artifact_runtime_preflight_validates_two_bindings(
    monkeypatch, tmp_path: Path
) -> None:
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    build_artifact(current, source=_source(tmp_path / "source-current", "current123"))
    build_artifact(previous, source=_source(tmp_path / "source-previous", "previous123"))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REACT_ADMIN_CURRENT_ARTIFACT_DIR", str(current))
    monkeypatch.setenv("REACT_ADMIN_PREVIOUS_ARTIFACT_DIR", str(previous))
    monkeypatch.setenv("REACT_ADMIN_ACTIVE_SELECTOR", "current")
    monkeypatch.setenv("ADMIN_ENTRY_TARGET_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(
        "scripts.launcher_preflight.attest_state",
        lambda _path: {
            "status": "ready",
            "registry_revision": "phase5a-mapped-entries-v2-system-status",
            "entry_count": 12,
            "receipt_count": 0,
        },
    )

    report = inspect_profile("artifact-runtime")

    assert report["status"] == "ready"
    assert report["artifact_attestation"]["active_selector"] == "current"
    assert report["entry_target_attestation"]["entry_count"] == 12
    assert report["streamlit_rollback"]["status"] == "retained"


def test_artifact_runtime_preflight_fails_closed_without_bindings(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    for name in (
        "ADMIN_ENTRY_TARGET_STATE_PATH",
        "REACT_ADMIN_CURRENT_ARTIFACT_DIR",
        "REACT_ADMIN_PREVIOUS_ARTIFACT_DIR",
        "REACT_ADMIN_ACTIVE_SELECTOR",
    ):
        monkeypatch.delenv(name, raising=False)

    report = inspect_profile("artifact-runtime")

    assert report["status"] == "blocked"
    assert "Admin entry target runtime state attestation" in report["missing"]["configuration"]

"""
File: test_admin_entry_target_runtime_launcher_contract.py
Description: 驗證 artifact-runtime launcher 在 child 啟動前執行 12-entry 唯讀 attestation。
"""

from pathlib import Path

from scripts.launcher_preflight import inspect_profile
from subsystems.access.admin_entry_target_control import EntryTargetError


class _Runtime:
    def health_attestation(self) -> dict[str, object]:
        return {"healthy": True, "active_selector": "current"}


def test_artifact_runtime_requires_entry_target_attestation(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    seen: list[Path] = []
    monkeypatch.setenv("ADMIN_ENTRY_TARGET_STATE_PATH", str(state_path))
    monkeypatch.setattr(
        "scripts.launcher_preflight.attest_state",
        lambda path: seen.append(path)
        or {
            "status": "ready",
            "registry_revision": "phase5a-mapped-entries-v2-system-status",
            "entry_count": 12,
            "receipt_count": 0,
        },
    )
    monkeypatch.setattr(
        "scripts.launcher_preflight.load_react_admin_runtime_from_environment",
        lambda **_kwargs: _Runtime(),
    )

    report = inspect_profile("artifact-runtime")

    assert report["status"] == "ready"
    assert seen == [state_path]
    assert report["entry_target_attestation"]["entry_count"] == 12
    assert report["startup_order"][:2] == [
        "entry-target-preflight",
        "artifact-preflight",
    ]


def test_artifact_runtime_missing_state_path_fails_before_artifact(monkeypatch) -> None:
    called = False

    def load_runtime(**_kwargs):
        nonlocal called
        called = True
        return _Runtime()

    monkeypatch.delenv("ADMIN_ENTRY_TARGET_STATE_PATH", raising=False)
    monkeypatch.setattr(
        "scripts.launcher_preflight.load_react_admin_runtime_from_environment",
        load_runtime,
    )

    report = inspect_profile("artifact-runtime")

    assert report["status"] == "blocked"
    assert not called
    assert report["missing"]["configuration"] == [
        "Admin entry target runtime state attestation"
    ]


def test_artifact_runtime_rejects_invalid_state_without_artifact_start(
    monkeypatch, tmp_path: Path
) -> None:
    called = False

    def reject_state(_path: Path) -> dict[str, object]:
        raise EntryTargetError(
            "unavailable", "entry_target_registry_stale", "Entry target registry 已過期"
        )

    def load_runtime(**_kwargs):
        nonlocal called
        called = True
        return _Runtime()

    monkeypatch.setenv("ADMIN_ENTRY_TARGET_STATE_PATH", str(tmp_path / "legacy.json"))
    monkeypatch.setattr("scripts.launcher_preflight.attest_state", reject_state)
    monkeypatch.setattr(
        "scripts.launcher_preflight.load_react_admin_runtime_from_environment",
        load_runtime,
    )

    report = inspect_profile("artifact-runtime")

    assert report["status"] == "blocked"
    assert not called
    assert "entry_target_attestation" not in report

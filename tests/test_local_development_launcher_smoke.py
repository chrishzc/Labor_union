"""
File: test_local_development_launcher_smoke.py
Description: 驗證受控 Windows launcher smoke 的安全契約。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from scripts import smoke_local_development_launcher as smoke
from infrastructure.http.private_operations_client import ReactAdminArtifactAttestation


ROOT = Path(__file__).resolve().parents[1]


class _ProcessStub:
    def __init__(self, return_code: int | None = None) -> None:
        self.return_code = return_code

    def poll(self) -> int | None:
        return self.return_code


def test_wait_until_ready_rejects_a_worker_that_exits_early(monkeypatch) -> None:
    monkeypatch.setattr(smoke.time, "monotonic", lambda: 0)

    with pytest.raises(RuntimeError, match="line-worker"):
        smoke._wait_until_ready({"line-worker": _ProcessStub(1)}, timeout_seconds=1)


def test_run_smoke_cleans_partially_started_services(monkeypatch) -> None:
    process = _ProcessStub()
    handle = BytesIO()
    stopped: list[dict[str, _ProcessStub]] = []

    def fail_during_start(processes, handles, run_dir, timeout_seconds) -> set[int]:
        processes["api"] = process
        handles.append(handle)
        raise RuntimeError("startup failed")

    monkeypatch.setattr(smoke, "_require_free_port", lambda port: None)
    monkeypatch.setattr(smoke, "_clear_previous_logs", lambda: None)
    monkeypatch.setattr(
        smoke,
        "inspect_profile",
        lambda _profile: {"status": "ready", "missing": {}, "disabled": []},
    )
    monkeypatch.setattr(smoke, "_start_services", fail_during_start)
    monkeypatch.setattr(
        smoke,
        "_stop_processes",
        lambda processes, owned_listener_pids: stopped.append(dict(processes)),
    )

    with pytest.raises(RuntimeError, match="startup failed"):
        smoke.run_smoke()

    assert stopped == [{"api": process}]
    assert handle.closed


def test_service_commands_match_the_windows_launcher_modules(monkeypatch) -> None:
    commands = smoke._service_commands()

    assert tuple(commands) == ("api", "react")
    assert commands["api"][-2:] == ["--port", "8000"]
    assert commands["react"][-2:] == ["5173", "--strictPort"]


def test_service_commands_skip_unconfigured_line_worker(monkeypatch) -> None:
    commands = smoke._service_commands()

    assert all("worker" not in name for name in commands)
    assert "runtime-monitor" not in commands


def test_windows_launcher_generates_key_without_nested_python_quotes() -> None:
    source = (ROOT / "scripts/launchers/start_local_development.bat").read_text(
        encoding="utf-8"
    )

    assert "RandomNumberGenerator]::Create()" in source
    assert "in ('\"%PY%\" -c \"import secrets" not in source


def test_windows_launcher_waits_for_api_and_ui_before_workers() -> None:
    source = (ROOT / "scripts/launchers/start_local_development.bat").read_text(
        encoding="utf-8"
    )

    api_start = source.index('start "FastAPI Server"')
    api_ready = source.index('call :WAIT_FOR_HTTP "http://127.0.0.1:8000/health"')
    ui_start = source.index('start "React Admin UI"')
    ui_ready = source.index(
        'call :WAIT_FOR_HTTP "http://127.0.0.1:5173/admin/"'
    )
    first_worker = source.index('start "LINE Worker"')

    assert api_start < api_ready < ui_start < ui_ready < first_worker


def test_artifact_runtime_smoke_compares_local_and_private_attestation(monkeypatch) -> None:
    digest = "a" * 64
    attestation = {
        "active_selector": "current",
        "artifact_version": "react-admin-v1",
        "artifact_digest": digest,
        "manifest_digest": "b" * 64,
        "api_compatibility_revision": "api-v1",
        "root_marker_checked": True,
        "checked_asset_digest": "c" * 64,
        "healthy": True,
    }
    monkeypatch.setattr(smoke, "inspect_profile", lambda _profile: {
        "status": "ready", "missing": {}, "artifact_attestation": attestation,
        "streamlit_rollback": {"status": "retained"},
    })

    class Client:
        def __init__(self, service_name: str) -> None:
            assert service_name == "runtime-monitor"

        def react_admin_artifact_health(self):
            return ReactAdminArtifactAttestation(**attestation)

    result = smoke.run_artifact_runtime_smoke(Client)

    assert result["status"] == "passed"
    assert result["get_only"] is True
    assert result["non_get_requests"] == 0
    assert result["side_effects"] == "none"

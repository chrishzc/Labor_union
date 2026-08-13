"""Safety contracts for the controlled Windows launcher smoke."""

from __future__ import annotations

from io import BytesIO

import pytest

from scripts import smoke_local_development_launcher as smoke


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

    def fail_during_start(processes, handles) -> None:
        processes["api"] = process
        handles.append(handle)
        raise RuntimeError("startup failed")

    monkeypatch.setattr(smoke, "_require_free_port", lambda port: None)
    monkeypatch.setattr(smoke, "_clear_previous_logs", lambda: None)
    monkeypatch.setattr(smoke, "_start_services", fail_during_start)
    monkeypatch.setattr(smoke, "_stop_processes", lambda processes: stopped.append(dict(processes)))

    with pytest.raises(RuntimeError, match="startup failed"):
        smoke.run_smoke()

    assert stopped == [{"api": process}]
    assert handle.closed


def test_service_commands_match_the_windows_launcher_modules(monkeypatch) -> None:
    monkeypatch.setattr(smoke, "_knowledge_worker_enabled", lambda: False)
    monkeypatch.setattr(smoke, "inspect_profile", lambda profile: {"status": "ready"})

    commands = smoke._service_commands()

    assert commands["line-worker"][-1] == "scripts.run_line_worker"
    assert commands["runtime-monitor"][-1] == "scripts.run_service_monitor"
    assert commands["durable-worker"][-1] == "scripts.run_durable_job_worker"
    assert commands["file-watcher"][-1] == "scripts/file_watcher.py"


def test_service_commands_skip_unconfigured_line_worker(monkeypatch) -> None:
    monkeypatch.setattr(smoke, "_knowledge_worker_enabled", lambda: False)
    monkeypatch.setattr(smoke, "inspect_profile", lambda profile: {"status": "blocked"})

    assert "line-worker" not in smoke._service_commands()

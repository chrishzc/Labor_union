"""Start the Windows local service set, verify it, then stop owned processes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from typing import BinaryIO
from urllib.request import urlopen

from scripts.launcher_preflight import inspect_profile


ROOT = Path(__file__).resolve().parents[1]
LOG_DIRECTORY = ROOT / "scratch" / "wp75-launcher-smoke" / "logs"
READY_URLS = {
    "api": "http://127.0.0.1:8000/health",
    "streamlit": "http://127.0.0.1:8501/_stcore/health",
}


def _service_commands() -> dict[str, list[str]]:
    python = sys.executable
    commands = {
        "api": [python, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        "streamlit": [python, "-m", "streamlit", "run", "ui/app.py", "--server.address", "127.0.0.1", "--server.port", "8501"],
        "runtime-monitor": [python, "-m", "scripts.run_service_monitor"],
        "file-watcher": [python, "scripts/file_watcher.py"],
        "durable-worker": [python, "-m", "scripts.run_durable_job_worker"],
        "incident-worker": [python, "-m", "scripts.run_incident_worker"],
    }
    if inspect_profile("line-worker")["status"] == "ready":
        commands["line-worker"] = [python, "-m", "scripts.run_line_worker"]
    if _knowledge_worker_enabled():
        commands["knowledge-worker"] = [python, "-m", "scripts.run_knowledge_worker"]
    return commands


def _knowledge_worker_enabled() -> bool:
    environment = ROOT / ".env"
    if not environment.is_file():
        return False
    return any(
        line.strip().casefold() == "knowledge_retrieval_runtime_enabled=true"
        for line in environment.read_text(encoding="utf-8").splitlines()
    )


def _require_free_port(port: int) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"local smoke port is already in use: {port}") from exc


def _start_services(
    processes: dict[str, subprocess.Popen[bytes]], handles: list[BinaryIO]
) -> None:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    commands = _service_commands()
    _start_service("api", commands.pop("api"), processes, handles)
    _wait_for_service_url(processes["api"], READY_URLS["api"], 30)
    _start_service("streamlit", commands.pop("streamlit"), processes, handles)
    _wait_for_service_url(processes["streamlit"], READY_URLS["streamlit"], 30)
    for name, command in commands.items():
        _start_service(name, command, processes, handles)


def _start_service(name, command, processes, handles) -> None:
    handle = (LOG_DIRECTORY / f"{name}.log").open("wb")
    handles.append(handle)
    processes[name] = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def _wait_for_service_url(process, url: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"local smoke service exited before readiness: {url}")
        if _url_ready(url):
            return
        time.sleep(0.25)
    raise RuntimeError(f"local smoke service readiness timed out: {url}")


def _clear_previous_logs() -> None:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for log_path in LOG_DIRECTORY.glob("*.log"):
        log_path.unlink()


def _url_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def _wait_until_ready(
    processes: dict[str, subprocess.Popen[bytes]], timeout_seconds: int
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        stopped = [name for name, process in processes.items() if process.poll() is not None]
        if stopped:
            raise RuntimeError("local smoke process exited early: " + ",".join(stopped))
        if all(_url_ready(url) for url in READY_URLS.values()):
            time.sleep(3)
            return
        time.sleep(1)
    raise RuntimeError("local launcher smoke readiness timed out")


def _stop_processes(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    for process in reversed(tuple(processes.values())):
        if process.poll() is not None:
            continue
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    for process in processes.values():
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def run_smoke(timeout_seconds: int = 45) -> dict[str, object]:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("INTERNAL_SERVICE_SHARED_KEY", secrets.token_urlsafe(32))
    for port in (8000, 8501):
        _require_free_port(port)
    _clear_previous_logs()
    processes: dict[str, subprocess.Popen[bytes]] = {}
    handles: list[BinaryIO] = []
    try:
        _start_services(processes, handles)
        _wait_until_ready(processes, timeout_seconds)
        return {
            "status": "passed", "services": tuple(processes),
            "health_urls": READY_URLS,
            "line_worker": "started" if "line-worker" in processes else "skipped-unconfigured",
            "logs": str(LOG_DIRECTORY),
        }
    finally:
        _stop_processes(processes)
        for handle in handles:
            handle.close()


def main() -> int:
    try:
        result = run_smoke()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

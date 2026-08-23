"""Phase 5B 三服務 GET-only smoke；只清理由本次 run 建立的 process。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import asdict
import secrets
import signal
import shutil
import socket
import subprocess
import sys
import time
from typing import BinaryIO
from urllib.error import HTTPError
from urllib.request import urlopen

from scripts.launcher_preflight import inspect_profile
from infrastructure.http.private_operations_client import PrivateOperationsClient


ROOT = Path(__file__).resolve().parents[1]
READY_URLS = {
    "api": "http://127.0.0.1:8000/health",
    "streamlit": "http://127.0.0.1:8501/_stcore/health",
    "react": "http://127.0.0.1:5173/",
}
PORTS = (8000, 8501, 5173)


def _service_commands() -> dict[str, list[str]]:
    python = sys.executable
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm") or "npm"
    return {
        "api": [python, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        "streamlit": [python, "-m", "streamlit", "run", "ui/app.py", "--server.address", "127.0.0.1", "--server.port", "8501"],
        "react": [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
    }


def _knowledge_worker_enabled() -> bool:
    """保留舊 smoke inventory API；Phase5B 不會依設定啟動 worker。"""
    return False


def _clear_previous_logs() -> None:
    """Phase5B logs are unique per run; intentionally never remove prior evidence."""
    return None


def _require_free_port(port: int) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"dual-run port is already in use: {port}") from exc


def _url_response(url: str) -> tuple[int, str, str]:
    try:
        with urlopen(url, timeout=2) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return response.status, response.headers.get("content-type", ""), body
    except HTTPError as error:
        body = error.read(4096).decode("utf-8", errors="replace")
        return error.code, error.headers.get("content-type", ""), body


def _react_ready() -> bool:
    status, content_type, body = _url_response(READY_URLS["react"])
    return status == 200 and "html" in content_type.casefold() and 'id="root"' in body


def _wait_for_service(name: str, process: subprocess.Popen[bytes], timeout: int = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited before readiness")
        try:
            ready = _react_ready() if name == "react" else _url_response(READY_URLS[name])[0] == 200
        except OSError:
            ready = False
        if ready:
            return
        time.sleep(0.25)
    raise RuntimeError(f"{name} readiness timed out")


def _start_service(name: str, command: list[str], run_dir: Path, processes: dict[str, subprocess.Popen[bytes]], handles: list[BinaryIO]) -> None:
    handle = (run_dir / f"{name}.log").open("wb")
    handles.append(handle)
    kwargs: dict[str, object] = {"cwd": ROOT, "stdout": handle, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        if Path(command[0]).suffix.casefold() in {".bat", ".cmd"}:
            command = [
                os.environ.get("COMSPEC", "cmd.exe"),
                "/d",
                "/c",
                "call",
                *command,
            ]
    else:
        kwargs["start_new_session"] = True
    if name == "react":
        kwargs["cwd"] = ROOT / "ui_react"
    processes[name] = subprocess.Popen(command, **kwargs)


def _windows_listener_pid(port: int) -> int | None:
    if os.name != "nt":
        return None
    output = subprocess.check_output(
        ["netstat", "-ano", "-p", "tcp"],
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    suffix = f":{port}"
    for line in output.splitlines():
        parts = line.split()
        if (
            len(parts) >= 5
            and parts[0].upper() == "TCP"
            and parts[1].endswith(suffix)
            and parts[3].upper() == "LISTENING"
        ):
            return int(parts[4])
    return None


def _stop_processes(
    processes: dict[str, subprocess.Popen[bytes]],
    owned_listener_pids: set[int] | None = None,
) -> None:
    for process in reversed(tuple(processes.values())):
        if process.poll() is not None:
            continue
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    if os.name == "nt":
        for pid in sorted(owned_listener_pids or set(), reverse=True):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    for process in processes.values():
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _start_services(
    processes: dict[str, subprocess.Popen[bytes]],
    handles: list[BinaryIO],
    run_dir: Path,
    timeout_seconds: int,
) -> set[int]:
    owned_listener_pids: set[int] = set()
    for (name, command), port in zip(_service_commands().items(), PORTS, strict=True):
        _start_service(name, command, run_dir, processes, handles)
        _wait_for_service(name, processes[name], timeout_seconds)
        listener_pid = _windows_listener_pid(port)
        if listener_pid is not None:
            owned_listener_pids.add(listener_pid)
    return owned_listener_pids


def _wait_until_ready(processes: dict[str, subprocess.Popen[bytes]], timeout_seconds: int) -> None:
    """Compatibility helper for callers that already spawned the controlled services."""
    for name, process in processes.items():
        _wait_for_service(name, process, timeout_seconds)


def _proxy_check() -> dict[str, object]:
    try:
        status, content_type, _ = _url_response(
            "http://127.0.0.1:5173/api/v1/system/status/performance-snapshot"
        )
        return {"status": "passed" if 200 <= status < 500 else "failed", "http_status": status, "content_type": content_type}
    except OSError as exc:
        return {"status": "failed", "error": str(exc)}


def run_smoke(timeout_seconds: int = 45) -> dict[str, object]:
    preflight = inspect_profile("dual-run")
    if preflight["status"] != "ready":
        raise RuntimeError("dual-run preflight blocked: " + json.dumps(preflight["missing"], ensure_ascii=False))
    for port in PORTS:
        _require_free_port(port)
    run_dir = ROOT / "scratch" / "phase5b-dual-run" / secrets.token_hex(8)
    run_dir.mkdir(parents=True, exist_ok=False)
    processes: dict[str, subprocess.Popen[bytes]] = {}
    owned_listener_pids: set[int] = set()
    handles: list[BinaryIO] = []
    started_at = time.time()
    result: dict[str, object]
    try:
        _clear_previous_logs()
        owned_listener_pids = _start_services(
            processes, handles, run_dir, timeout_seconds
        )
        proxy = _proxy_check()
        if proxy["status"] != "passed":
            raise RuntimeError("React relative /api proxy failed")
        result = {
            "status": "passed",
            "run_id": run_dir.name,
            "services": list(processes),
            "owned_listener_pids": sorted(owned_listener_pids),
            "ports": list(PORTS),
            "ready": {name: True for name in processes},
            "proxy": proxy,
            "disabled": preflight["disabled"],
            "get_only": True,
            "non_get_requests": 0,
            "logs": str(run_dir),
            "duration_seconds": round(time.time() - started_at, 3),
        }
    finally:
        _stop_processes(processes, owned_listener_pids)
        for handle in handles:
            handle.close()
    time.sleep(0.25)
    for port in PORTS:
        _require_free_port(port)
    result["owned_cleanup"] = {str(port): True for port in PORTS}
    return result


def run_artifact_runtime_smoke(
    client_factory=PrivateOperationsClient,
) -> dict[str, object]:
    """Compare pre-child local validation with the mounted read-only attestation."""
    preflight = inspect_profile("artifact-runtime")
    if preflight["status"] != "ready":
        raise RuntimeError(
            "artifact-runtime preflight blocked: "
            + json.dumps(preflight["missing"], ensure_ascii=False)
        )
    remote = client_factory("runtime-monitor").react_admin_artifact_health()
    local = preflight["artifact_attestation"]
    remote_data = asdict(remote)
    identity_fields = (
        "active_selector",
        "artifact_version",
        "artifact_digest",
        "manifest_digest",
        "api_compatibility_revision",
        "checked_asset_digest",
    )
    if any(local[field] != remote_data[field] for field in identity_fields):
        raise RuntimeError("mounted React admin artifact identity differs from preflight")
    return {
        "status": "passed",
        "profile": "artifact-runtime",
        "attestation": remote_data,
        "streamlit_rollback": preflight["streamlit_rollback"],
        "get_only": True,
        "non_get_requests": 0,
        "side_effects": "none",
    }


def main() -> int:
    artifact_runtime = "--artifact-runtime" in sys.argv[1:]
    try:
        result = run_artifact_runtime_smoke() if artifact_runtime else run_smoke()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "get_only": True, "non_get_requests": 0}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

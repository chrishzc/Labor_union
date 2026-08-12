"""Ephemeral candidate-runtime ports for a preserve-data rehearsal."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RehearsalRuntimeError(RuntimeError):
    """A candidate-only runtime target did not become safely readable."""


@dataclass(frozen=True, slots=True)
class CandidateRuntimeConfig:
    project_root: Path
    api_port: int
    streamlit_port: int
    startup_timeout_seconds: int
    database_environment: Mapping[str, str]
    database_config: Any
    candidate_database: str
    evidence_directory: Path


class EphemeralCandidateRestartPort:
    def __init__(self, config: CandidateRuntimeConfig) -> None:
        self._config = config
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._logs: dict[str, Path] = {}

    def restart(self, target: str) -> Mapping[str, Any]:
        if target == "api":
            return self._start_http_target(target, self._api_command(), "/health")
        if target == "streamlit":
            return self._start_http_target(target, self._streamlit_command(), "/")
        if target == "file-watcher":
            return self._start_background_target(target, self._watcher_command())
        if target == "background-worker":
            return self._run_idle_worker_once()
        raise RehearsalRuntimeError(f"unsupported restart target: {target}")

    def shutdown(self) -> tuple[Mapping[str, Any], ...]:
        receipts = []
        for target in reversed(tuple(self._processes)):
            process = self._processes.pop(target)
            receipts.append(_terminate_process(target, process, self._logs[target]))
        return tuple(receipts)

    def _start_http_target(self, target, command, path):
        process = self._start_process(target, command)
        _wait_for_http(_base_url(self._port_for(target)) + path, process, self._config.startup_timeout_seconds)
        return _started_receipt(target, process, self._logs[target], endpoint=path)

    def _start_background_target(self, target, command):
        process = self._start_process(target, command)
        time.sleep(0.5)
        if process.poll() is not None:
            raise RehearsalRuntimeError(f"{target} exited before readiness")
        return _started_receipt(target, process, self._logs[target])

    def _run_idle_worker_once(self):
        _require_no_active_jobs(self._config.database_config, self._config.candidate_database)
        target = "background-worker"
        process = self._start_process(target, self._worker_command())
        try:
            process.wait(timeout=self._config.startup_timeout_seconds)
        except subprocess.TimeoutExpired as error:
            raise RehearsalRuntimeError("background worker did not finish its idle check") from error
        if process.returncode != 0:
            raise RehearsalRuntimeError("background worker idle check failed")
        return _started_receipt(target, process, self._logs[target], completed_once=True)

    def _start_process(self, target, command):
        if target in self._processes:
            raise RehearsalRuntimeError(f"restart target already started: {target}")
        self._config.evidence_directory.mkdir(parents=True, exist_ok=True)
        log_path = self._config.evidence_directory / f"{target}.log"
        log_handle = log_path.open("wb")
        try:
            process = subprocess.Popen(
                command,
                cwd=self._config.project_root,
                env=_runtime_environment(self._config.database_environment),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        finally:
            log_handle.close()
        self._processes[target] = process
        self._logs[target] = log_path
        return process

    def _api_command(self):
        return [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(self._config.api_port)]

    def _streamlit_command(self):
        return [sys.executable, "-m", "streamlit", "run", "ui/app.py", "--server.address", "127.0.0.1", "--server.port", str(self._config.streamlit_port), "--server.headless", "true"]

    def _watcher_command(self):
        return [sys.executable, "scripts/file_watcher.py"]

    def _worker_command(self):
        return [sys.executable, "-m", "scripts.run_durable_job_worker", "--once", "--worker-id", "preserve-rehearsal"]

    def _port_for(self, target):
        return self._config.api_port if target == "api" else self._config.streamlit_port


class CandidateReadSmokePort:
    def __init__(self, config: CandidateRuntimeConfig) -> None:
        self._config = config

    def run(self, smoke_id: str) -> Mapping[str, Any]:
        path = self._path_for(smoke_id)
        response_status, body = _read_http(
            _base_url(self._config.api_port) + path,
            headers=_read_smoke_headers(),
            accepted_statuses=self._accepted_statuses(smoke_id),
        )
        return {
            "status": "passed",
            "smoke_id": smoke_id,
            "path": path,
            "response_status": response_status,
            "empty_dataset": response_status == 404,
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "response_bytes": len(body),
        }

    def _path_for(self, smoke_id):
        if smoke_id == "orders-read":
            return "/api/v1/orders/summaries?page_size=1"
        if smoke_id == "finance-import-read":
            return "/api/v1/finance-import/batches?limit=1"
        if smoke_id == "scheduling-read":
            return f"/api/v1/scheduling/staff/{self._staff_id()}/current-calendar?range_start=2026-01-01&range_end=2026-01-01"
        if smoke_id == "payroll-payables-read":
            return f"/api/v1/payroll/staff/{self._staff_id()}/obligations"
        if smoke_id == "anomalies-read":
            return "/api/v1/anomalies?limit=1&offset=0"
        raise RehearsalRuntimeError(f"unsupported smoke id: {smoke_id}")

    def _accepted_statuses(self, smoke_id):
        if smoke_id in {"scheduling-read", "payroll-payables-read"}:
            return frozenset({200, 404})
        return frozenset({200})

    def _staff_id(self):
        connection = self._config.database_config.connect(self._config.candidate_database)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM staff ORDER BY id LIMIT 1")
                row = cursor.fetchone()
        finally:
            connection.close()
        if not row:
            return 1
        if int(row["id"]) < 1:
            raise RehearsalRuntimeError("candidate staff identifier is invalid")
        return int(row["id"])


def _runtime_environment(database_environment):
    environment = os.environ.copy()
    environment.update(database_environment)
    environment.update(
        {
            "APP_ENV": "test",
            "ENABLE_ADMIN_AUTH": "false",
            "PRESERVE_DATA_REHEARSAL_READ_ONLY": "true",
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _require_no_active_jobs(database_config, candidate_database):
    connection = database_config.connect(candidate_database)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM background_jobs WHERE status IN ('queued','running')")
            row = cursor.fetchone()
    finally:
        connection.close()
    if not row or int(row["count"]) != 0:
        raise RehearsalRuntimeError("candidate has active durable jobs")


def _wait_for_http(url, process, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RehearsalRuntimeError(f"runtime exited before HTTP readiness: {url}")
        try:
            _read_http(url)
            return
        except (URLError, HTTPError):
            time.sleep(0.2)
    raise RehearsalRuntimeError(f"runtime did not become readable: {url}")


def _read_http(url, headers=None, accepted_statuses=frozenset({200})):
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=5) as response:
            status = response.status
            body = response.read()
    except HTTPError as error:
        if error.code not in accepted_statuses:
            raise
        return error.code, error.read()
    if status not in accepted_statuses:
        raise RehearsalRuntimeError(f"read smoke returned HTTP {status}: {url}")
    return status, body


def _base_url(port):
    return f"http://127.0.0.1:{port}"


def _started_receipt(target, process, log_path, **extra):
    return {"status": "passed", "target": target, "pid": process.pid, "log_path": str(log_path), **extra}


def _terminate_process(target, process, log_path):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    return {"status": "passed", "target": target, "exit_code": process.returncode, "log_path": str(log_path)}

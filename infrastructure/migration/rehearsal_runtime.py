"""
File: rehearsal_runtime.py
Description: 提供 preserve-data rehearsal 的 ephemeral FastAPI、React 與 worker runtime ports。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class RehearsalRuntimeError(RuntimeError):
    """A candidate-only runtime target did not become safely readable."""


@dataclass(frozen=True, slots=True)
class CandidateRuntimeConfig:
    project_root: Path
    api_port: int
    react_port: int
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
        # Historical migration manifests may still carry the removed UI target
        # name. It is normalized to the current React runtime; no Streamlit
        # process, source, dependency, or rollback surface is restored.
        current_target = "react" if target in {"react", "streamlit"} else target
        if current_target == "api":
            return self._start_http_target(
                current_target, self._api_command(), "/health"
            )
        if current_target == "react":
            return self._start_http_target(
                current_target, self._react_command(), "/admin/"
            )
        if current_target == "background-worker":
            return self._run_idle_worker_once()
        raise RehearsalRuntimeError(f"unsupported restart target: {target}")

    def shutdown(self) -> tuple[Mapping[str, Any], ...]:
        receipts = []
        for target in reversed(tuple(self._processes)):
            process = self._processes.pop(target)
            receipts.append(
                _terminate_process(target, process, self._logs[target])
            )
        return tuple(receipts)

    def _start_http_target(
        self, target: str, command: list[str], path: str
    ) -> Mapping[str, Any]:
        process = self._start_process(target, command)
        _wait_for_http(
            _base_url(self._port_for(target)) + path,
            process,
            self._config.startup_timeout_seconds,
        )
        return _started_receipt(
            target, process, self._logs[target], endpoint=path
        )

    def _run_idle_worker_once(self) -> Mapping[str, Any]:
        _require_no_active_jobs(
            self._config.database_config, self._config.candidate_database
        )
        target = "background-worker"
        process = self._start_process(target, self._worker_command())
        try:
            process.wait(timeout=self._config.startup_timeout_seconds)
        except subprocess.TimeoutExpired as error:
            raise RehearsalRuntimeError(
                "background worker did not finish its idle check"
            ) from error
        if process.returncode != 0:
            raise RehearsalRuntimeError("background worker idle check failed")
        return _started_receipt(
            target,
            process,
            self._logs[target],
            completed_once=True,
        )

    def _start_process(
        self, target: str, command: list[str]
    ) -> subprocess.Popen[bytes]:
        if target in self._processes:
            raise RehearsalRuntimeError(
                f"restart target already started: {target}"
            )
        self._config.evidence_directory.mkdir(parents=True, exist_ok=True)
        log_path = self._config.evidence_directory / f"{target}.log"
        log_handle = log_path.open("wb")
        try:
            process = subprocess.Popen(
                command,
                cwd=self._config.project_root,
                env=_runtime_environment(
                    self._config.database_environment
                ),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        finally:
            log_handle.close()
        self._processes[target] = process
        self._logs[target] = log_path
        return process

    def _api_command(self) -> list[str]:
        return [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(self._config.api_port),
        ]

    def _react_command(self) -> list[str]:
        npm = shutil.which("npm")
        if npm is None:
            raise RehearsalRuntimeError(
                "npm is required for React candidate rehearsal"
            )
        return [
            npm,
            "--prefix",
            str(self._config.project_root / "ui_react"),
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(self._config.react_port),
            "--strictPort",
        ]

    def _worker_command(self) -> list[str]:
        return [
            sys.executable,
            "-m",
            "scripts.run_durable_job_worker",
            "--once",
            "--worker-id",
            "preserve-rehearsal",
        ]

    def _port_for(self, target: str) -> int:
        return (
            self._config.api_port
            if target == "api"
            else self._config.react_port
        )


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

    def _path_for(self, smoke_id: str) -> str:
        if smoke_id == "orders-read":
            return "/api/v1/orders/summaries?page_size=1"
        if smoke_id == "finance-import-read":
            return "/api/v1/finance-import/batches?limit=1"
        if smoke_id == "scheduling-read":
            return (
                f"/api/v1/scheduling/staff/{self._staff_id()}"
                "/current-calendar?range_start=2026-01-01&range_end=2026-01-01"
            )
        if smoke_id == "payroll-payables-read":
            return (
                f"/api/v1/payroll/staff/{self._staff_id()}/obligations"
            )
        if smoke_id == "anomalies-read":
            return "/api/v1/anomalies?limit=1&offset=0"
        if smoke_id == "historical-service-accounting-query":
            case_no = quote(
                self._historical_service_accounting_case_no(), safe=""
            )
            return (
                f"/api/v1/orders/{case_no}/historical-service-accounting"
            )
        raise RehearsalRuntimeError(
            f"unsupported smoke id: {smoke_id}"
        )

    def _accepted_statuses(self, smoke_id: str) -> frozenset[int]:
        if smoke_id in {
            "scheduling-read",
            "payroll-payables-read",
            "historical-service-accounting-query",
        }:
            return frozenset({200, 404})
        return frozenset({200})

    def _historical_service_accounting_case_no(self) -> str:
        connection = self._config.database_config.connect(
            self._config.candidate_database
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT case_no FROM orders "
                    "WHERE status='歷史訂單－服務完成' "
                    "ORDER BY case_no LIMIT 1"
                )
                row = cursor.fetchone()
        finally:
            connection.close()
        return (
            str(row["case_no"])
            if row and str(row.get("case_no") or "").strip()
            else "__migration_empty_historical_case__"
        )

    def _staff_id(self) -> int:
        connection = self._config.database_config.connect(
            self._config.candidate_database
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM staff ORDER BY id LIMIT 1")
                row = cursor.fetchone()
        finally:
            connection.close()
        if not row:
            return 1
        if int(row["id"]) < 1:
            raise RehearsalRuntimeError(
                "candidate staff identifier is invalid"
            )
        return int(row["id"])


def _runtime_environment(
    database_environment: Mapping[str, str]
) -> dict[str, str]:
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


def _read_smoke_headers() -> dict[str, str]:
    return {}


def _require_no_active_jobs(
    database_config: Any, candidate_database: str
) -> None:
    connection = database_config.connect(candidate_database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM background_jobs "
                "WHERE status IN ('queued','running')"
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    if not row or int(row["count"]) != 0:
        raise RehearsalRuntimeError(
            "candidate has active durable jobs"
        )


def _wait_for_http(
    url: str,
    process: subprocess.Popen[bytes],
    timeout_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RehearsalRuntimeError(
                f"runtime exited before HTTP readiness: {url}"
            )
        try:
            _read_http(url)
            return
        except (URLError, HTTPError):
            time.sleep(0.2)
    raise RehearsalRuntimeError(
        f"runtime did not become readable: {url}"
    )


def _read_http(
    url: str,
    headers: Mapping[str, str] | None = None,
    accepted_statuses: frozenset[int] = frozenset({200}),
) -> tuple[int, bytes]:
    request = Request(url, headers=dict(headers or {}))
    try:
        with urlopen(request, timeout=5) as response:
            status = response.status
            body = response.read()
    except HTTPError as error:
        if error.code not in accepted_statuses:
            raise
        return error.code, error.read()
    if status not in accepted_statuses:
        raise RehearsalRuntimeError(
            f"read smoke returned HTTP {status}: {url}"
        )
    return status, body


def _base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _started_receipt(
    target: str,
    process: subprocess.Popen[bytes],
    log_path: Path,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "status": "passed",
        "target": target,
        "pid": process.pid,
        "log_path": str(log_path),
        **extra,
    }


def _terminate_process(
    target: str,
    process: subprocess.Popen[bytes],
    log_path: Path,
) -> dict[str, Any]:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    return {
        "status": "passed",
        "target": target,
        "exit_code": process.returncode,
        "log_path": str(log_path),
    }
